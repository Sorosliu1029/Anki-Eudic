"""Anki package (``.apkg``) export, optionally enriched from the LDOCE5++ dictionary.

Re-exporting the same study list updates notes in place: the note type ID is fixed,
each note's GUID derives from its word only, and Anki matches decks by name. See
``docs/anki-development.md`` for the import rules this relies on.
"""

from __future__ import annotations

import hashlib
import html
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import genanki

from .dictionary import DictionaryEntry, Sense
from .models import Word

# Never change these: a new model ID or field list makes Anki import a second note type
# and stop updating existing notes. Templates and CSS may change freely.
MODEL_ID = 1_761_189_143
GUID_NAMESPACE = "anki-eudic"
FIELDS = (
    "Word",
    "PhoneticUK",
    "PhoneticUS",
    "AudioUK",
    "AudioUS",
    "PartOfSpeech",
    "Definition",
    "Explanation",
    "Context",
    "Extra",
    "Added",
    "Star",
)

MAX_SENSES = 8
MAX_EXAMPLES = 2
MAX_COLLOCATIONS = 12

_FRONT = """\
<div class="word">{{Word}}</div>
<div class="phonetic">
<span class="pron">{{#PhoneticUK}}<span class="accent">BrE</span> {{PhoneticUK}}{{/PhoneticUK}} \
{{AudioUK}}</span>
<span class="pron">{{#PhoneticUS}}<span class="accent">AmE</span> {{PhoneticUS}}{{/PhoneticUS}} \
{{AudioUS}}</span>
</div>
"""
_BACK = """\
{{FrontSide}}
<hr id="answer">
{{#Definition}}<div class="definition" \
onclick="var p = event.target.closest('.reveal'); if (p) p.classList.toggle('shown');">\
{{Definition}}</div>{{/Definition}}
{{#Explanation}}<div class="explanation">{{Explanation}}</div>{{/Explanation}}
{{#Context}}<div class="context">{{Context}}</div>{{/Context}}
{{#Extra}}<div class="extra">{{Extra}}</div>{{/Extra}}
"""
_CSS = """\
.card { font-family: -apple-system, "Segoe UI", sans-serif; font-size: 18px;
  text-align: left; max-width: 46em; margin: 0 auto; }
.word { font-size: 2em; font-weight: 600; text-align: center; }
.phonetic { color: #666; text-align: center; margin-bottom: .8em; }
.pron { white-space: nowrap; margin: 0 .6em; }
.accent { font-size: .7em; font-weight: 600; color: #2a6db0; }
.pos { font-style: italic; color: #b03060; font-weight: 600; }
.signpost { background: #2a6db0; color: #fff; font-size: .75em; padding: 0 .3em;
  border-radius: 3px; text-transform: uppercase; }
.gram { color: #2e8b57; }
.labels { color: #8a6d00; font-style: italic; }
.tran { color: #777; }
.reveal > .tran { display: none; }
.reveal.shown > .tran { display: inline; }
.reveal > .en { cursor: pointer; text-decoration: underline dotted #bbb; }
.examples { color: #444; font-style: italic; }
.explanation, .context, .extra { border-top: 1px solid #ddd; margin-top: .8em;
  padding-top: .5em; }
.context { font-style: italic; }
.extra { font-size: .85em; color: #555; }
.nightMode .phonetic, .nightMode .tran, .nightMode .examples, .nightMode .extra { color: #aaa; }
"""

MODEL = genanki.Model(
    MODEL_ID,
    "Anki-Eudic Word",
    fields=[{"name": name} for name in FIELDS],
    templates=[{"name": "Recognize", "qfmt": _FRONT, "afmt": _BACK}],
    css=_CSS,
)


class Dictionary(Protocol):
    """What the exporter needs from :class:`~anki_eudic.dictionary.LdoceDictionary`."""

    def lookup(self, word: str) -> DictionaryEntry | None: ...

    def resource(self, path: str) -> bytes | None: ...


@dataclass(frozen=True, slots=True)
class ExportSummary:
    path: Path
    notes: int
    enriched: int  # notes filled from the dictionary
    audio: int  # media files bundled


def note_guid(word: str) -> str:
    """Identify a note by its word alone, so content changes update rather than duplicate."""
    return genanki.guid_for(GUID_NAMESPACE, word.strip().casefold())


def deck_id(name: str) -> int:
    """Derive a stable deck ID; Anki itself matches decks by name on import."""
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big") >> 2


def media_name(path: str) -> str:
    """Map ``media/english/breProns/x.mp3`` to an ASCII-safe ``ldoce_breProns_x.mp3``."""
    parts = path.replace("\\", "/").rstrip("/").split("/")
    stem = "_".join(parts[-2:])
    return "ldoce_" + re.sub(r"[^A-Za-z0-9._-]+", "_", stem)


def _field(value: str) -> str:
    """Escape untrusted API content and preserve visual line breaks in Anki."""
    return (
        html.escape(value, quote=False)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
        .replace("\t", "    ")
    )


def _text(value: str) -> str:
    return html.escape(value, quote=False)


def _ipa(value: str) -> str:
    return f"/{_text(value)}/" if value else ""


def _span(css: str, value: str) -> str:
    return f'<span class="{css}">{_text(value)}</span>' if value else ""


def _grammar(code: str) -> str:
    return f"[{code}]" if code and not code.startswith("[") else code


def _reveal(css: str, english: str, translation: str) -> str:
    """Pair English with its translation, which the card shows only after a click."""
    if not english or not translation:
        return _span(css, english) or _span("tran", translation)
    return (
        f'<span class="reveal"><span class="{css} en">{_text(english)}</span> '
        f"{_span('tran', translation)}</span>"
    )


def _render_sense(sense: Sense) -> str:
    definition = sense.definition or "; ".join(ref.text for ref in sense.cross_references)
    parts = [
        _span("signpost", sense.signpost),
        f"<b>{_text(sense.lexical_unit)}</b>" if sense.lexical_unit else "",
        _span("gram", _grammar(sense.grammar)),
        _span("labels", ", ".join(sense.labels)),
        _reveal("def", definition, sense.translation),
    ]
    body = " ".join(part for part in parts if part)
    examples = [
        f"<li>{_reveal('example', ex.text, ex.translation)}</li>"
        for ex in sense.examples[:MAX_EXAMPLES]
    ]
    if examples:
        body += '<ul class="examples">' + "".join(examples) + "</ul>"
    if sense.subsenses:
        items = "".join(f"<li>{_render_sense(sub)}</li>" for sub in sense.subsenses)
        body += f'<ol type="a">{items}</ol>'
    return body


def render_entry(entry: DictionaryEntry) -> dict[str, str]:
    """Render an LDOCE entry into the HTML of its note fields (all but audio and Eudic's)."""
    pronunciation = entry.pronunciation
    blocks = []
    for homograph in entry.homographs:
        head = " ".join(
            part
            for part in (
                _span("pos", homograph.part_of_speech),
                _span("gram", _grammar(homograph.grammar)),
            )
            if part
        )
        senses = [s for s in homograph.senses if s.definition or s.subsenses or s.cross_references]
        items = "".join(f"<li>{_render_sense(s)}</li>" for s in senses[:MAX_SENSES])
        if head or items:
            blocks.append(f"<div>{head}<ol>{items}</ol></div>" if items else f"<div>{head}</div>")
    collocations = list(
        dict.fromkeys(c.phrase for h in entry.homographs for c in h.collocations if c.phrase)
    )
    extra = []
    if collocations:
        extra.append("<b>Collocations:</b> " + _text(", ".join(collocations[:MAX_COLLOCATIONS])))
    extra += [_text(origin) for origin in entry.origins]
    return {
        "PhoneticUK": _ipa(pronunciation.ipa_bre),
        "PhoneticUS": _ipa(pronunciation.ipa_ame),
        "PartOfSpeech": _text(", ".join(entry.parts_of_speech)),
        "Definition": "".join(blocks),
        "Extra": "<br>".join(extra),
    }


def export_apkg(
    words: Iterable[Word],
    destination: str | Path,
    deck: str = "Eudic",
    dictionary: Dictionary | None = None,
    *,
    audio: bool = True,
) -> ExportSummary:
    """Write an Anki package, adding LDOCE content when ``dictionary`` is given.

    Words found in the dictionary use its content instead of Eudic's explanation. With
    ``audio``, pronunciations are read via ``dictionary.resource`` and bundled.
    """
    path = Path(destination).expanduser().with_suffix(".apkg")
    path.parent.mkdir(parents=True, exist_ok=True)
    anki_deck = genanki.Deck(deck_id(deck), deck)
    notes = enriched = 0
    with tempfile.TemporaryDirectory(prefix="anki-eudic-") as media_dir:
        media: dict[str, Path] = {}

        def sound(resource: str) -> str:
            if not resource or dictionary is None or not audio:
                return ""
            name = media_name(resource)
            if name not in media:
                data = dictionary.resource(resource)
                if data is None:
                    return ""
                media[name] = Path(media_dir, name)
                media[name].write_bytes(data)
            return f"[sound:{name}]"

        for item in words:
            fields: dict[str, str] = dict.fromkeys(FIELDS, "")
            fields.update(
                Word=_field(item.word),
                PhoneticUK=_ipa(item.phonetic),
                Explanation=_field(item.explanation),
                Context=_field(item.context),
                Added=_field(item.added_at),
                Star=str(item.star),
            )
            entry = dictionary.lookup(item.word) if dictionary is not None else None
            if entry is not None and entry.homographs:
                rendered = render_entry(entry)
                fields.update({key: value for key, value in rendered.items() if value})
                fields["Explanation"] = ""
                fields["AudioUK"] = sound(entry.pronunciation.audio_bre)
                fields["AudioUS"] = sound(entry.pronunciation.audio_ame)
                enriched += 1
            anki_deck.add_note(
                genanki.Note(
                    model=MODEL,
                    fields=[fields[name] for name in FIELDS],
                    guid=note_guid(item.word),
                )
            )
            notes += 1
        package = genanki.Package(anki_deck, media_files=[str(p) for p in media.values()])
        package.write_to_file(str(path))
    return ExportSummary(path, notes, enriched, len(media))
