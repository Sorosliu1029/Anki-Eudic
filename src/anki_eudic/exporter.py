"""Anki text-file export."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Iterable

from .models import Word


def _field(value: str) -> str:
    """Escape untrusted API content and preserve visual line breaks in Anki."""
    return (
        html.escape(value, quote=False)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
        .replace("\t", "    ")
    )


def export_anki(words: Iterable[Word], destination: str | Path, deck: str = "Eudic") -> int:
    """Write an Anki-importable UTF-8 TSV and return the number of notes."""
    path = Path(destination).expanduser()
    if path.suffix.lower() not in {".tsv", ".txt"}:
        path = path.with_suffix(".tsv")
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as output:
        output.write("#separator:Tab\n#html:true\n")
        safe_deck = deck.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        output.write(f"#deck:{safe_deck}\n")
        output.write("#columns:Word\tDefinition\tContext\tPhonetic\tAdded\tStar\n")
        for item in words:
            output.write(
                "\t".join(
                    [
                        _field(item.word),
                        _field(item.explanation),
                        _field(item.context),
                        _field(item.phonetic),
                        _field(item.added_at),
                        str(item.star),
                    ]
                )
                + "\n"
            )
            count += 1
    return count
