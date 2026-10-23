"""Textual interface for exporting Eudic vocabulary."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from .auth import CredentialError, load_token
from .client import EudicClient, EudicError
from .models import Category, Word
from .screens import Connection, ExportScreen, ExportSettings, TokenScreen, default_dictionary


def matches(word: Word, query: str) -> bool:
    """Case-insensitively match ``query`` against the word, explanation or context."""
    needle = query.strip().casefold()
    return not needle or any(
        needle in field.casefold() for field in (word.word, word.explanation, word.context)
    )


def _one_line(value: str, limit: int = 80) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class AnkiEudicApp(App[None]):
    """Browse Eudic study lists and export one to Anki."""

    TITLE = "Anki Eudic"
    SUB_TITLE = "Study-list exporter"
    CSS = """
    #body { height: 1fr; }
    #sidebar { width: 34; border-right: vkey $primary-background; }
    .pane-title { text-style: bold; color: $accent; padding: 0 1; height: 1; }
    #lists { height: 1fr; border: none; }
    #main { width: 1fr; }
    #toolbar { height: 3; padding: 0 1; }
    #summary { width: 1fr; height: 3; content-align: left middle; }
    #filter { width: 36; }
    #preview { height: 1fr; }
    #detail-pane { height: 9; border-top: hkey $primary-background; padding: 0 1; }
    """
    BINDINGS: ClassVar[list[Binding | tuple[str, str, str]]] = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("e", "export", "Export"),
        Binding("slash", "focus_filter", "Filter", key_display="/"),
        ("t", "token", "Token"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None
        self.categories: list[Category] = []
        self.cache: dict[str, list[Word]] = {}
        self.category: Category | None = None
        self.words: list[Word] = []
        self.shown: list[Word] = []
        self.settings = ExportSettings(
            destination=str(Path.cwd() / "eudic-words.apkg"), dictionary=default_dictionary()
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Label("Study lists", classes="pane-title")
                yield OptionList(id="lists")
            with Vertical(id="main"):
                with Horizontal(id="toolbar"):
                    yield Static("", id="summary")
                    yield Input(placeholder="Filter words  ( / )", id="filter")
                yield DataTable(id="preview", zebra_stripes=True, cursor_type="row")
                with VerticalScroll(id="detail-pane"):
                    yield Static("", id="detail")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#preview", DataTable)
        table.add_column("Word", width=20)
        table.add_column("Phonetic", width=16)
        table.add_column("★", width=3)
        table.add_column("Explanation")
        try:
            self.token = load_token()
        except CredentialError as exc:
            self.notify(str(exc), severity="error", timeout=10)
        if self.token:
            self.load_categories()
        else:
            self._summary("Not connected — press [b]t[/b] to add your Eudic token.")
            self.action_token()

    # Display helpers

    def _summary(self, message: str) -> None:
        self.query_one("#summary", Static).update(message)

    def _error(self, message: str) -> None:
        self.notify(message, title="Error", severity="error", timeout=8)

    def _show_categories(self) -> None:
        lists = self.query_one("#lists", OptionList)
        lists.clear_options()
        lists.add_options(
            Option(f"{item.name} ({item.language})", id=item.id) for item in self.categories
        )
        if not self.categories:
            self._summary("Your Eudic account has no study lists.")
        elif len(self.categories) == 1:
            self.open_category(self.categories[0])
        else:
            self._summary("Select a study list to preview its words.")
            lists.highlighted = 0
            lists.focus()

    def _show_words(self) -> None:
        query = self.query_one("#filter", Input).value
        self.shown = [item for item in self.words if matches(item, query)]
        table = self.query_one("#preview", DataTable)
        table.clear()
        for index, item in enumerate(self.shown):
            table.add_row(
                item.word,
                item.phonetic,
                str(item.star or ""),
                _one_line(item.explanation),
                key=str(index),
            )
        self._show_detail(0)
        if self.category is not None:
            count = (
                f"{len(self.shown)} of {len(self.words)} words"
                if query.strip()
                else f"{len(self.words)} words"
            )
            self._summary(f"[b]{self.category.name}[/b] · {count}")
        self.refresh_bindings()

    def _show_detail(self, row: int) -> None:
        detail = self.query_one("#detail", Static)
        if not self.shown or not 0 <= row < len(self.shown):
            detail.update(Text("No word selected.", style="dim") if self.words else "")
            return
        item = self.shown[row]
        text = Text()
        text.append(item.word, style="bold")
        if item.phonetic:
            text.append(f"  /{item.phonetic.strip('/')}/", style="italic")
        if item.star:
            text.append("  " + "★" * item.star, style="yellow")
        if item.added_at:
            text.append(f"  added {item.added_at}", style="dim")
        if item.explanation:
            text.append("\n" + item.explanation.strip())
        if item.context:
            text.append("\nContext: ", style="bold")
            text.append(item.context.strip())
        detail.update(text)

    # Events

    @on(OptionList.OptionSelected, "#lists")
    def _list_selected(self, event: OptionList.OptionSelected) -> None:
        category = next((item for item in self.categories if item.id == event.option.id), None)
        if category is not None:
            self.open_category(category)

    @on(Input.Changed, "#filter")
    def _filter_changed(self) -> None:
        self._show_words()

    @on(Input.Submitted, "#filter")
    def _filter_submitted(self) -> None:
        self.query_one("#preview", DataTable).focus()

    @on(DataTable.RowHighlighted, "#preview")
    def _row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_detail(event.cursor_row)

    def on_key(self, event: events.Key) -> None:
        filter_input = self.query_one("#filter", Input)
        if event.key == "escape" and self.focused is filter_input:
            filter_input.value = ""
            self.query_one("#preview", DataTable).focus()
            event.stop()

    # Actions

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if isinstance(self.screen, ModalScreen):
            return action not in {"quit", "refresh", "export", "focus_filter", "token"}
        if action == "export":
            return bool(self.words)
        return True

    def action_refresh(self) -> None:
        if self.token:
            self.load_categories()
        else:
            self.action_token()

    def action_focus_filter(self) -> None:
        self.query_one("#filter", Input).focus()

    def action_token(self) -> None:
        if not isinstance(self.screen, TokenScreen):
            self.push_screen(TokenScreen(has_token=bool(self.token)), self._connected)

    def action_export(self) -> None:
        if self.words and self.category is not None:
            self.push_screen(ExportScreen(self.words, self.category.name, self.settings))

    def _connected(self, connection: Connection | None) -> None:
        if connection is None:
            if not self.token:
                self._summary("Not connected — press [b]t[/b] to add your Eudic token.")
            return
        self.token = connection.token
        self.categories = connection.categories
        self.cache.clear()
        self.notify(f"Connected. Loaded {len(self.categories)} study list(s).")
        self._show_categories()

    # Workers

    @work(thread=True, exclusive=True, group="api")
    def load_categories(self) -> None:
        lists = self.query_one("#lists", OptionList)
        self.call_from_thread(setattr, lists, "loading", True)
        try:
            with EudicClient(self.token or "") as client:
                categories = client.categories()
        except EudicError as exc:
            self.call_from_thread(self._error, str(exc))
            self.call_from_thread(self._summary, "Could not load study lists — press [b]r[/b].")
            return
        finally:
            self.call_from_thread(setattr, lists, "loading", False)
        self.categories = categories
        self.cache.clear()
        self.call_from_thread(self._show_categories)

    def open_category(self, category: Category) -> None:
        self.category = category
        if category.id in self.cache:
            self.words = self.cache[category.id]
            self._show_words()
            self.query_one("#preview", DataTable).focus()
        else:
            self.words = []
            self._show_words()
            self.fetch_words(category)

    @work(thread=True, exclusive=True, group="api")
    def fetch_words(self, category: Category) -> None:
        table = self.query_one("#preview", DataTable)
        self.call_from_thread(setattr, table, "loading", True)
        self.call_from_thread(self._summary, f"Loading “{category.name}”…")
        try:
            with EudicClient(self.token or "") as client:
                words = client.words(category.id, category.language)
        except EudicError as exc:
            self.call_from_thread(self._error, str(exc))
            self.call_from_thread(self._summary, f"Could not load “{category.name}”.")
            return
        finally:
            self.call_from_thread(setattr, table, "loading", False)
        self.cache[category.id] = words
        self.call_from_thread(self._words_loaded, category, words)

    def _words_loaded(self, category: Category, words: list[Word]) -> None:
        if self.category != category:
            return
        self.words = words
        self._show_words()
        self.query_one("#preview", DataTable).focus()


def main() -> None:
    AnkiEudicApp().run()


if __name__ == "__main__":
    main()
