"""Modal screens: connecting to Eudic and exporting to Anki."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ProgressBar, Static

from .apkg import ExportSummary, export_apkg
from .auth import ENV_VAR, CredentialError, delete_token, normalize_token, save_token
from .client import EudicClient, EudicError
from .dictionary import LdoceDictionary
from .mdict import MdictError
from .models import Category, Word

DICTIONARY_ENV = "ANKI_EUDIC_LDOCE"

MODAL_CSS = """
TokenScreen, ExportScreen { align: center middle; background: $background 70%; }
.dialog {
    width: 80; max-width: 95%; height: auto; max-height: 95%;
    padding: 1 2; border: thick $primary; background: $surface;
}
.dialog-title { text-style: bold; color: $accent; margin-bottom: 1; }
.dialog .help { color: $text-muted; margin-bottom: 1; }
.dialog Input { margin-bottom: 0; }
.dialog .field { margin-top: 1; }
.dialog .error { color: $error; margin-top: 1; }
.dialog .buttons { height: auto; margin-top: 1; align-horizontal: right; }
.dialog .buttons Button { margin-left: 1; width: auto; min-width: 10; }
"""


def default_dictionary() -> str:
    """Return ``$ANKI_EUDIC_LDOCE`` or an LDOCE5++ ``.mdx`` in Eudic's macOS library, if any."""
    if configured := os.environ.get(DICTIONARY_ENV):
        return configured
    found = sorted((Path.home() / "Library" / "Eudb_en").glob("LDOCE5*.mdx"))
    return str(found[0]) if found else ""


def describe_dictionary(value: str) -> tuple[bool, str]:
    """Return whether an export may use ``value`` as the ``.mdx`` path, and a hint for it."""
    if not value.strip():
        return True, "Not set — cards use Eudic's data only."
    path = Path(value.strip()).expanduser()
    if not path.is_file():
        return False, "✗ File not found."
    if path.with_suffix(".mdd").is_file():
        return True, "✓ Adds definitions and pronunciation audio."
    return True, "✓ Adds definitions (no .mdd next to it, so no audio)."


@dataclass(frozen=True, slots=True)
class Connection:
    token: str
    categories: list[Category]


@dataclass(slots=True)
class ExportSettings:
    destination: str
    deck: str = "Eudic"
    dictionary: str = ""


class TokenScreen(ModalScreen[Connection | None]):
    """Ask for a Eudic token, verify it by loading the study lists, then save it."""

    CSS = MODAL_CSS
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [("escape", "cancel", "Cancel")]

    def __init__(self, *, has_token: bool) -> None:
        super().__init__()
        self.has_token = has_token

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label("Connect to Eudic", classes="dialog-title")
            yield Static(
                "Paste the authorization token from Eudic's Open API page "
                "(my.eudic.net). With or without the 'NIS ' prefix is fine.",
                classes="help",
            )
            yield Input(placeholder="Eudic API token", password=True, id="token")
            yield Static(
                "Saved tokens go only to your operating system's credential store. "
                f"To avoid saving, use it once or set {ENV_VAR}.",
                classes="help field",
            )
            yield Static("", id="token-error", classes="error")
            with Horizontal(classes="buttons"):
                if self.has_token:
                    yield Button("Forget saved token", variant="warning", id="forget")
                yield Button("Cancel", id="cancel")
                yield Button("Use without saving", id="use-once")
                yield Button("Save & connect", variant="primary", id="save")

    def on_mount(self) -> None:
        self.query_one("#token-error", Static).display = False
        self.query_one("#token", Input).focus()

    def _error(self, message: str) -> None:
        error = self.query_one("#token-error", Static)
        error.update(message)
        error.display = bool(message)

    def _set_busy(self, busy: bool) -> None:
        for widget in self.query("Input, Button"):
            widget.disabled = busy
        self.query_one("#save", Button).label = "Connecting…" if busy else "Save & connect"

    @on(Input.Submitted, "#token")
    @on(Button.Pressed, "#save")
    def _save(self) -> None:
        self._connect(persist=True)

    @on(Button.Pressed, "#use-once")
    def _use_once(self) -> None:
        self._connect(persist=False)

    @on(Button.Pressed, "#cancel")
    def action_cancel(self) -> None:
        if not self.query_one("#token", Input).disabled:
            self.dismiss(None)

    @on(Button.Pressed, "#forget")
    def _forget(self) -> None:
        try:
            delete_token()
        except CredentialError as exc:
            self._error(str(exc))
            return
        self.app.notify(f"Saved token removed. A {ENV_VAR} value is unaffected.")
        self.query_one("#forget", Button).remove()

    def _connect(self, *, persist: bool) -> None:
        try:
            token = normalize_token(self.query_one("#token", Input).value)
        except ValueError as exc:
            self._error(str(exc))
            return
        self._error("")
        self._set_busy(True)
        self.verify(token, persist)

    @work(thread=True, exclusive=True)
    def verify(self, token: str, persist: bool) -> None:
        try:
            with EudicClient(token) as client:
                categories = client.categories()
            if persist:
                save_token(token)
        except (EudicError, CredentialError) as exc:
            self.app.call_from_thread(self._failed, str(exc))
            return
        self.app.call_from_thread(self.dismiss, Connection(token, categories))

    def _failed(self, message: str) -> None:
        self._set_busy(False)
        self._error(message)
        self.query_one("#token", Input).focus()


class ExportScreen(ModalScreen[None]):
    """Choose the deck, file and dictionary, then export with a progress bar."""

    CSS = (
        MODAL_CSS
        + """
    #dictionary-hint { color: $text-muted; }
    #dictionary-hint.invalid { color: $error; }
    #progress { margin-top: 1; }
    #result { margin-top: 1; color: $success; }
    """
    )
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [("escape", "close", "Close")]

    def __init__(self, words: list[Word], list_name: str, settings: ExportSettings) -> None:
        super().__init__()
        self.words = words
        self.list_name = list_name
        self.settings = settings
        self.running = False

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(
                f"Export {len(self.words)} word(s) from “{self.list_name}”",
                classes="dialog-title",
            )
            yield Label("Anki deck", classes="field")
            yield Input(value=self.settings.deck, placeholder="Eudic", id="deck")
            yield Label("Output file (.apkg)", classes="field")
            yield Input(value=self.settings.destination, id="destination")
            yield Label("LDOCE5++ dictionary (.mdx, optional)", classes="field")
            yield Input(
                value=self.settings.dictionary,
                placeholder=f"Path to LDOCE5++ .mdx — default from {DICTIONARY_ENV}",
                id="dictionary",
            )
            yield Static("", id="dictionary-hint")
            yield ProgressBar(total=len(self.words), id="progress")
            yield Static("", id="result")
            yield Static("", id="export-error", classes="error")
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="close")
                yield Button("Export", variant="success", id="export")

    def on_mount(self) -> None:
        for selector in ("#progress", "#result", "#export-error"):
            self.query_one(selector).display = False
        self._check_dictionary(self.settings.dictionary)
        self.query_one("#export", Button).focus()

    @on(Input.Changed, "#dictionary")
    def _dictionary_changed(self, event: Input.Changed) -> None:
        self._check_dictionary(event.value)

    def _check_dictionary(self, value: str) -> bool:
        ok, hint = describe_dictionary(value)
        widget = self.query_one("#dictionary-hint", Static)
        widget.update(hint)
        widget.set_class(not ok, "invalid")
        return ok

    def _error(self, message: str) -> None:
        error = self.query_one("#export-error", Static)
        error.update(message)
        error.display = bool(message)

    @on(Button.Pressed, "#close")
    def action_close(self) -> None:
        if not self.running:
            self.dismiss(None)

    @on(Input.Submitted)
    @on(Button.Pressed, "#export")
    def _export(self) -> None:
        if self.running:
            return
        destination = self.query_one("#destination", Input).value.strip()
        deck = self.query_one("#deck", Input).value.strip() or "Eudic"
        dictionary = self.query_one("#dictionary", Input).value.strip()
        if not destination:
            self._error("Choose an output file.")
            return
        if not self._check_dictionary(dictionary):
            self._error("The dictionary file was not found. Fix the path or clear it.")
            return
        self.settings.destination, self.settings.deck = destination, deck
        self.settings.dictionary = dictionary
        self._error("")
        self.query_one("#result").display = False
        progress = self.query_one("#progress", ProgressBar)
        progress.update(progress=0)
        progress.display = True
        self._set_running(True)
        self.export_package(destination, deck, dictionary)

    def _set_running(self, running: bool) -> None:
        self.running = running
        for widget in self.query("Input, Button"):
            widget.disabled = running

    @work(thread=True, exclusive=True)
    def export_package(self, destination: str, deck: str, mdx: str) -> None:
        def advance(done: int) -> None:
            self.app.call_from_thread(
                self.query_one("#progress", ProgressBar).update, progress=done
            )

        try:
            if mdx:
                mdx_path = Path(mdx).expanduser()
                mdd_path = mdx_path.with_suffix(".mdd")
                has_audio = mdd_path.is_file()
                with LdoceDictionary(mdx_path, mdd_path if has_audio else None) as dictionary:
                    summary = export_apkg(
                        self.words, destination, deck, dictionary, audio=has_audio, progress=advance
                    )
            else:
                summary = export_apkg(self.words, destination, deck, progress=advance)
        except (OSError, MdictError) as exc:
            self.app.call_from_thread(self._failed, f"Could not write the export: {exc}")
        else:
            self.app.call_from_thread(self._finished, summary, bool(mdx))

    def _failed(self, message: str) -> None:
        self._set_running(False)
        self.query_one("#progress").display = False
        self._error(message)

    def _finished(self, summary: ExportSummary, used_dictionary: bool) -> None:
        self._set_running(False)
        enriched = (
            f", {summary.enriched} enriched from LDOCE with {summary.audio} audio file(s)"
            if used_dictionary
            else ""
        )
        result = self.query_one("#result", Static)
        result.update(
            f"Exported {summary.notes} note(s){enriched} to {summary.path}.\n"
            "In Anki choose File → Import; re-importing updates existing notes."
        )
        result.display = True
        close = self.query_one("#close", Button)
        close.label, close.variant = "Done", "primary"
        close.focus()
        self.app.notify(f"Exported {summary.notes} note(s) to {summary.path.name}.")
