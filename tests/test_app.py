import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import ClassVar

import pytest
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, OptionList, ProgressBar, Static

from anki_eudic import app as app_module
from anki_eudic import screens
from anki_eudic.app import AnkiEudicApp, matches
from anki_eudic.client import EudicError
from anki_eudic.models import Category, Word
from anki_eudic.screens import ExportScreen, TokenScreen, describe_dictionary

CATEGORIES = [Category("0", "Unknown", "en"), Category("1", "Hard", "en")]
WORDS = {
    "0": [
        Word("abate", "əˈbeɪt", "v. 减弱", "The storm abated.", "2026-09-14", 3),
        Word("zeal", "ziːl", "n. 热情"),
    ],
    "1": [Word("quell", explanation="v. 平息")],
}


class FakeClient:
    tokens: ClassVar[list[str]] = []
    valid = "NIS good"

    def __init__(self, token: str) -> None:
        self.token = token
        FakeClient.tokens.append(token)

    def __enter__(self) -> "FakeClient":  # noqa: PYI034
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def _check(self) -> None:
        if self.token != self.valid:
            raise EudicError("Eudic rejected the token.")

    def categories(self) -> list[Category]:
        self._check()
        return CATEGORIES

    def words(self, category_id: str, language: str) -> list[Word]:
        self._check()
        return WORDS[category_id]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, list[str]]:
    saved: dict[str, list[str]] = {"tokens": []}
    FakeClient.tokens = []
    monkeypatch.setattr(app_module, "EudicClient", FakeClient)
    monkeypatch.setattr(screens, "EudicClient", FakeClient)
    monkeypatch.setattr(screens, "save_token", saved["tokens"].append)
    monkeypatch.setattr(app_module, "default_dictionary", lambda: "")
    monkeypatch.chdir(tmp_path)
    return saved


Scenario = Callable[[AnkiEudicApp, Pilot], Awaitable[None]]


def run(scenario: Scenario) -> None:
    async def main() -> None:
        app = AnkiEudicApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(main())


async def settle(app: AnkiEudicApp, pilot: Pilot) -> None:
    await app.workers.wait_for_complete()
    for worker_screen in app.screen_stack:
        await worker_screen.workers.wait_for_complete()
    await pilot.pause()


def rows(app: AnkiEudicApp) -> list[str]:
    table = app.query_one("#preview", DataTable)
    return [str(table.get_row_at(index)[0]) for index in range(table.row_count)]


def test_matches_word_explanation_and_context() -> None:
    word = Word("abate", explanation="v. 减弱", context="The storm abated.")
    assert matches(word, "") and matches(word, "ABA") and matches(word, "减弱")
    assert matches(word, "storm") and not matches(word, "zeal")


def test_describe_dictionary(tmp_path: Path) -> None:
    mdx = tmp_path / "LDOCE5.mdx"
    assert describe_dictionary("") == (True, "Not set — cards use Eudic's data only.")
    assert describe_dictionary(str(mdx))[0] is False
    mdx.write_bytes(b"")
    ok, hint = describe_dictionary(str(mdx))
    assert ok and "no audio" in hint
    mdx.with_suffix(".mdd").write_bytes(b"")
    assert describe_dictionary(str(mdx)) == (True, "✓ Adds definitions and pronunciation audio.")


def test_first_run_verifies_token_before_saving(env, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "load_token", lambda: None)

    async def scenario(app: AnkiEudicApp, pilot: Pilot) -> None:
        assert isinstance(app.screen, TokenScreen)
        app.screen.query_one("#token", Input).value = "bad"
        await pilot.press("enter")
        await settle(app, pilot)
        assert isinstance(app.screen, TokenScreen)
        assert "rejected" in str(app.screen.query_one("#token-error", Static).render())
        assert env["tokens"] == []

        app.screen.query_one("#token", Input).value = "good"
        await pilot.press("enter")
        await settle(app, pilot)
        assert not isinstance(app.screen, TokenScreen)
        assert env["tokens"] == ["NIS good"]
        assert app.query_one("#lists", OptionList).option_count == 2

    run(scenario)


def test_use_without_saving_does_not_store_token(env, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "load_token", lambda: None)

    async def scenario(app: AnkiEudicApp, pilot: Pilot) -> None:
        app.screen.query_one("#token", Input).value = "good"
        await pilot.click("#use-once")
        await settle(app, pilot)
        assert app.token == "NIS good" and env["tokens"] == []

    run(scenario)


def test_selecting_list_loads_words_and_filter_narrows(env, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "load_token", lambda: "NIS good")

    async def scenario(app: AnkiEudicApp, pilot: Pilot) -> None:
        await settle(app, pilot)
        assert not app.check_action("export", ())
        await pilot.press("enter")  # first list is highlighted
        await settle(app, pilot)
        assert rows(app) == ["abate", "zeal"]
        assert "Unknown" in str(app.query_one("#summary", Static).render())
        assert "The storm abated." in str(app.query_one("#detail", Static).render())
        assert app.check_action("export", ())

        await pilot.press("slash", "z", "e")
        assert rows(app) == ["zeal"]
        assert "1 of 2 words" in str(app.query_one("#summary", Static).render())
        await pilot.press("escape")
        assert rows(app) == ["abate", "zeal"]
        assert app.focused is app.query_one("#preview", DataTable)

        calls = len(FakeClient.tokens)
        app.open_category(CATEGORIES[1])
        await settle(app, pilot)
        app.open_category(CATEGORIES[0])
        await settle(app, pilot)
        assert rows(app) == ["abate", "zeal"]
        assert len(FakeClient.tokens) == calls + 1  # second visit came from the cache

    run(scenario)


def test_export_screen_writes_package(env, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(app_module, "load_token", lambda: "NIS good")

    async def scenario(app: AnkiEudicApp, pilot: Pilot) -> None:
        await settle(app, pilot)
        await pilot.press("enter")
        await settle(app, pilot)
        await pilot.press("e")
        assert isinstance(app.screen, ExportScreen)
        assert not app.check_action("export", ())  # no nested export screens

        app.screen.query_one("#dictionary", Input).value = str(tmp_path / "missing.mdx")
        await pilot.click("#export")
        await settle(app, pilot)
        assert "not found" in str(app.screen.query_one("#export-error", Static).render())

        app.screen.query_one("#dictionary", Input).value = ""
        app.screen.query_one("#deck", Input).value = "Mine"
        app.screen.query_one("#deck", Input).focus()
        await pilot.press("enter")
        await settle(app, pilot)
        assert (tmp_path / "eudic-words.apkg").is_file()
        assert app.screen.query_one("#progress", ProgressBar).progress == 2
        assert "Exported 2 note(s)" in str(app.screen.query_one("#result", Static).render())
        assert app.settings.deck == "Mine"

        await pilot.press("escape")
        assert not isinstance(app.screen, ExportScreen)

    run(scenario)
