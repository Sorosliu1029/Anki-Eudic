"""Textual interface for exporting Eudic vocabulary."""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static

from .apkg import export_apkg
from .auth import CredentialError, delete_token, load_token, normalize_token, save_token
from .client import EudicClient, EudicError
from .dictionary import LdoceDictionary
from .exporter import export_anki
from .mdict import MdictError
from .models import Category, Word

DICTIONARY_ENV = "ANKI_EUDIC_LDOCE"
FORMATS = {"apkg": ".apkg", "tsv": ".tsv"}


def default_dictionary() -> str:
    """Return ``$ANKI_EUDIC_LDOCE`` or an LDOCE5++ ``.mdx`` in Eudic's macOS library, if any."""
    if configured := os.environ.get(DICTIONARY_ENV):
        return configured
    found = sorted((Path.home() / "Library" / "Eudb_en").glob("LDOCE5*.mdx"))
    return str(found[0]) if found else ""


class AnkiEudicApp(App[None]):
    """Fetch a Eudic study list, preview it, and export it for Anki."""

    TITLE = "Anki Eudic"
    SUB_TITLE = "Study-list exporter"
    CSS = """
    Screen { align: center top; }
    #content { width: 94%; max-width: 120; padding: 1 2; }
    .section { margin-top: 1; text-style: bold; color: $accent; }
    Input, Select { margin-bottom: 1; }
    Button { margin-right: 1; }
    #status { margin: 1 0; padding: 1; background: $surface; min-height: 3; }
    #preview { height: 1fr; min-height: 12; }
    #token-help, #dictionary-help { color: $text-muted; margin-bottom: 1; }
    """
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh lists"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None
        self.categories: list[Category] = []
        self.words: list[Word] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="content"):
            yield Label("1. Eudic authorization", classes="section")
            yield Input(
                placeholder="Paste an API token (optionally including the 'NIS ' prefix)",
                password=True,
                id="token",
            )
            yield Static(
                "Saved tokens go only to your operating system's credential store. "
                "Alternatively, set EUDIC_TOKEN for the current process.",
                id="token-help",
            )
            with Horizontal():
                yield Button("Save token", variant="primary", id="save-token")
                yield Button("Forget saved token", variant="warning", id="forget-token")
                yield Button("Load study lists", id="load-categories")
            yield Label("2. Select words", classes="section")
            yield Select([], prompt="Load and select a Eudic study list", id="category")
            with Horizontal():
                yield Button("Fetch words", variant="primary", id="fetch", disabled=True)
            yield Label("3. Export for Anki", classes="section")
            yield Select(
                [("Anki package (.apkg) with dictionary audio", "apkg"), ("Text (.tsv)", "tsv")],
                value="apkg",
                allow_blank=False,
                id="format",
            )
            yield Input(value=str(Path.cwd() / "eudic-words.apkg"), id="destination")
            yield Input(value="Eudic", placeholder="Anki deck name", id="deck")
            yield Input(
                value=default_dictionary(),
                placeholder="Optional LDOCE5++ .mdx path (adds definitions and audio)",
                id="dictionary",
            )
            yield Static(
                f"Used for .apkg only; the .mdd next to it supplies audio. Set {DICTIONARY_ENV} "
                "to change the default.",
                id="dictionary-help",
            )
            yield Button("Export", variant="success", id="export", disabled=True)
            yield Static("Ready. Add a token to begin.", id="status")
            yield DataTable(id="preview", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#preview", DataTable)
        table.add_columns("Word", "Phonetic", "Definition", "Context")
        try:
            self.token = load_token()
        except CredentialError as exc:
            self._status(str(exc), error=True)
            return
        if self.token:
            self._status("Token loaded from the environment or secure credential store.")
            self.load_categories()

    def _status(self, message: str, *, error: bool = False) -> None:
        prefix = "[bold red]Error:[/bold red] " if error else "[bold green]Status:[/bold green] "
        self.query_one("#status", Static).update(prefix + message)

    def _entered_or_loaded_token(self) -> str:
        entered = self.query_one("#token", Input).value
        if entered:
            return normalize_token(entered)
        if self.token:
            return self.token
        raise ValueError("Enter and save a Eudic API token first.")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "category":
            self.query_one("#fetch", Button).disabled = event.value is Select.BLANK
        elif event.select.id == "format" and event.value in FORMATS:
            destination = self.query_one("#destination", Input)
            if destination.value.strip():
                path = Path(destination.value.strip())
                destination.value = str(path.with_suffix(FORMATS[str(event.value)]))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "save-token":
                self._save_token()
            case "forget-token":
                self._forget_token()
            case "load-categories":
                self.load_categories()
            case "fetch":
                self.fetch_words()
            case "export":
                self._export()

    def _save_token(self) -> None:
        try:
            token = normalize_token(self.query_one("#token", Input).value)
            save_token(token)
        except (ValueError, CredentialError) as exc:
            self._status(str(exc), error=True)
            return
        self.token = token
        self.query_one("#token", Input).clear()
        self._status("Token saved securely. Its value has been cleared from the screen.")
        self.load_categories()

    def _forget_token(self) -> None:
        try:
            delete_token()
        except CredentialError as exc:
            self._status(str(exc), error=True)
            return
        self.token = None
        self.query_one("#token", Input).clear()
        self._status("Saved token removed. An EUDIC_TOKEN environment value is unaffected.")

    @work(thread=True, exclusive=True, group="api")
    def load_categories(self) -> None:
        try:
            token = self.call_from_thread(self._entered_or_loaded_token)
            with EudicClient(token) as client:
                categories = client.categories()
        except (ValueError, EudicError) as exc:
            self.call_from_thread(self._status, str(exc), error=True)
            return
        self.categories = categories
        self.call_from_thread(self._show_categories)

    def _show_categories(self) -> None:
        select = self.query_one("#category", Select)
        select.set_options((f"{item.name} ({item.language})", item.id) for item in self.categories)
        self._status(f"Loaded {len(self.categories)} study list(s). Choose one to continue.")

    @work(thread=True, exclusive=True, group="api")
    def fetch_words(self) -> None:
        selected = self.call_from_thread(lambda: self.query_one("#category", Select).value)
        if selected is Select.BLANK:
            self.call_from_thread(self._status, "Choose a study list first.", error=True)
            return
        category = next((item for item in self.categories if item.id == str(selected)), None)
        if category is None:
            self.call_from_thread(
                self._status, "The selected study list is no longer available.", error=True
            )
            return
        try:
            token = self.call_from_thread(self._entered_or_loaded_token)
            with EudicClient(token) as client:
                words = client.words(category.id, category.language)
        except (ValueError, EudicError) as exc:
            self.call_from_thread(self._status, str(exc), error=True)
            return
        self.words = words
        self.call_from_thread(self._show_words, category.name)

    def _show_words(self, category_name: str) -> None:
        table = self.query_one("#preview", DataTable)
        table.clear()
        for item in self.words[:500]:
            table.add_row(item.word, item.phonetic, item.explanation, item.context)
        self.query_one("#export", Button).disabled = not self.words
        suffix = " (preview limited to 500)" if len(self.words) > 500 else ""
        self._status(f"Fetched {len(self.words)} word(s) from “{category_name}”{suffix}.")

    def _export(self) -> None:
        destination = self.query_one("#destination", Input).value.strip()
        deck = self.query_one("#deck", Input).value.strip() or "Eudic"
        if not destination:
            self._status("Choose an export filename.", error=True)
            return
        if self.query_one("#format", Select).value == "tsv":
            self._export_tsv(destination, deck)
        else:
            mdx = self.query_one("#dictionary", Input).value.strip()
            self.query_one("#export", Button).disabled = True
            self._status("Exporting…" + (" Looking up words in LDOCE." if mdx else ""))
            self.export_package(destination, deck, mdx)

    def _export_tsv(self, destination: str, deck: str) -> None:
        try:
            count = export_anki(self.words, destination, deck)
        except OSError as exc:
            self._status(f"Could not write the export: {exc}", error=True)
            return
        path = Path(destination).expanduser()
        if path.suffix.lower() not in {".tsv", ".txt"}:
            path = path.with_suffix(".tsv")
        self._status(
            f"Exported {count} note(s) to {path}. Import it in Anki as tab-separated text."
        )

    @work(thread=True, exclusive=True, group="export")
    def export_package(self, destination: str, deck: str, mdx: str) -> None:
        try:
            if mdx:
                mdx_path = Path(mdx).expanduser()
                if not mdx_path.is_file():
                    raise FileNotFoundError(f"Dictionary not found: {mdx_path}")
                mdd_path = mdx_path.with_suffix(".mdd")
                has_audio = mdd_path.is_file()
                with LdoceDictionary(mdx_path, mdd_path if has_audio else None) as dictionary:
                    summary = export_apkg(
                        self.words, destination, deck, dictionary, audio=has_audio
                    )
            else:
                summary = export_apkg(self.words, destination, deck)
        except (OSError, MdictError) as exc:
            self.call_from_thread(self._status, f"Could not write the export: {exc}", error=True)
        else:
            enriched = (
                f", {summary.enriched} enriched from LDOCE with {summary.audio} audio file(s)"
                if mdx
                else ""
            )
            self.call_from_thread(
                self._status,
                f"Exported {summary.notes} note(s){enriched} to {summary.path}. "
                "Import it in Anki with File → Import; re-importing updates existing notes.",
            )
        finally:
            self.call_from_thread(self._enable_export)

    def _enable_export(self) -> None:
        self.query_one("#export", Button).disabled = not self.words

    def action_refresh(self) -> None:
        self.load_categories()


def main() -> None:
    AnkiEudicApp().run()


if __name__ == "__main__":
    main()
