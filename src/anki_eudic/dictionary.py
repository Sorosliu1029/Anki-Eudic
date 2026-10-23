"""Look up words in a local LDOCE5++ MDict dictionary (``.mdx`` + ``.mdd``).

``parse_entry_html`` turns one LDOCE5++ entry page into plain dataclasses; the
``LdoceDictionary`` facade adds key lookup, ``@@@LINK=`` redirects and audio extraction.
Text fields are plain text (no HTML), so they can later be escaped into Anki fields.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import PreformattedString

from .mdict import MdictFile

if TYPE_CHECKING:
    from typing_extensions import Self

_LINK_PREFIX = "@@@LINK="
_MAX_REDIRECTS = 5

# Elements that start a new, separately parsed unit; sense-level searches stop there.
_SENSE_BOUNDARY = frozenset(
    {
        "Sense",
        "Subsense",
        "GramExa",
        "ColloExa",
        "lm5ppBox",
        "EXAMPLE",
        "Crossref",
        "crossRef",
        "Thesref",
        "SpokenSect",
    }
)
# Inline elements that need a space before them when flattened to text.
_SPACED = frozenset(
    {
        "GRAM",
        "lm5pp_POS",
        "OBJECT",
        "EXP",
        "DEF",
        "COLLGLOSS",
        "GLOSS",
        "GEO",
        "REGISTERLAB",
        "LANG",
        "ORIGIN",
        "CENTURY",
        "TRAN",
        "DERIV",
        "EXPR",
        "REFSENSENUM",
    }
)
# Elements that start a new line inside usage/thesaurus boxes.
_BOX_BLOCKS = frozenset(
    {"EXAMPLE", "Exponent", "Section", "SECHEADING", "EXPL", "BADEXA", "Collocate", "dont_say"}
)
_IGNORED = frozenset({"cn_txt", "foldsign", "HYP", "speaker"})
_BREAK = "\x00"


@dataclass(frozen=True, slots=True)
class Pronunciation:
    """IPA and ``.mdd`` audio paths (e.g. ``media/english/breProns/x.mp3``)."""

    ipa_bre: str = ""
    ipa_ame: str = ""
    audio_bre: str = ""
    audio_ame: str = ""


@dataclass(frozen=True, slots=True)
class Example:
    text: str
    translation: str = ""
    audio: str = ""


@dataclass(frozen=True, slots=True)
class Collocation:
    """A grammar pattern or collocation, with optional gloss and examples."""

    phrase: str
    kind: str = "collocation"  # "grammar" or "collocation"
    gloss: str = ""
    translation: str = ""
    group: str = ""  # collocation-box section, such as "verbs" or "adjectives"
    examples: tuple[Example, ...] = ()


@dataclass(frozen=True, slots=True)
class CrossReference:
    """A pointer such as "comparative of dry"; ``target`` is the headword to look up."""

    text: str
    target: str = ""


@dataclass(frozen=True, slots=True)
class Sense:
    number: str = ""
    signpost: str = ""
    lexical_unit: str = ""
    grammar: str = ""
    labels: tuple[str, ...] = ()
    activator: str = ""
    definition: str = ""
    translation: str = ""
    synonyms: tuple[str, ...] = ()
    opposites: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    examples: tuple[Example, ...] = ()
    patterns: tuple[Collocation, ...] = ()
    subsenses: tuple[Sense, ...] = ()
    cross_references: tuple[CrossReference, ...] = ()


@dataclass(frozen=True, slots=True)
class Note:
    """A usage box such as THESAURUS or GRAMMAR, flattened to lines of text."""

    title: str
    text: str


@dataclass(frozen=True, slots=True)
class Homograph:
    """One numbered headword entry, usually one part of speech."""

    headword: str
    homograph: str = ""
    part_of_speech: str = ""
    grammar: str = ""
    pronunciation: Pronunciation = field(default_factory=Pronunciation)
    inflections: tuple[str, ...] = ()
    frequency: tuple[str, ...] = ()
    level: str = ""
    academic: bool = False
    topics: tuple[str, ...] = ()
    senses: tuple[Sense, ...] = ()
    phrasal_verbs: tuple[Sense, ...] = ()
    derived_forms: tuple[str, ...] = ()
    collocations: tuple[Collocation, ...] = ()
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True, slots=True)
class DictionaryEntry:
    query: str
    headword: str
    homographs: tuple[Homograph, ...]
    word_family: tuple[tuple[str, tuple[str, ...]], ...] = ()
    origins: tuple[str, ...] = ()
    redirected_from: str = ""

    @property
    def pronunciation(self) -> Pronunciation:
        for homograph in self.homographs:
            if homograph.pronunciation.ipa_bre:
                return homograph.pronunciation
        return self.homographs[0].pronunciation if self.homographs else Pronunciation()

    @property
    def parts_of_speech(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(h.part_of_speech for h in self.homographs if h.part_of_speech))

    def audio_paths(self) -> tuple[str, ...]:
        """Return every referenced ``.mdd`` audio path, without duplicates."""
        paths: list[str] = []
        for homograph in self.homographs:
            paths += [homograph.pronunciation.audio_bre, homograph.pronunciation.audio_ame]
            for sense in homograph.senses + homograph.phrasal_verbs:
                paths += _sense_audio(sense)
        return tuple(dict.fromkeys(path for path in paths if path))


def _sense_audio(sense: Sense) -> list[str]:
    paths = [example.audio for example in sense.examples]
    for pattern in sense.patterns:
        paths += [example.audio for example in pattern.examples]
    for subsense in sense.subsenses:
        paths += _sense_audio(subsense)
    return paths


# --- HTML helpers ------------------------------------------------------------------


def _classes(element: Tag) -> set[str]:
    return set(element.get("class") or ())


def _own(
    element: Tag, wanted: Iterable[str], stop: frozenset[str] = _SENSE_BOUNDARY
) -> Iterator[Tag]:
    """Yield descendants with a ``wanted`` class without entering ``stop`` elements."""
    wanted = set(wanted)
    for child in element.children:
        if not isinstance(child, Tag):
            continue
        classes = _classes(child)
        if classes & wanted:
            yield child
        elif not classes & stop:
            yield from _own(child, wanted, stop)


def _first(element: Tag, wanted: str, stop: frozenset[str] = _SENSE_BOUNDARY) -> Tag | None:
    return next(_own(element, {wanted}, stop), None)


def _clean(text: str) -> str:
    return " ".join(text.split())


def _text(
    element: Tag | None, skip: frozenset[str] = _IGNORED, blocks: frozenset[str] = frozenset()
) -> str:
    """Flatten an element to text, skipping Chinese translations and decorations."""
    if element is None:
        return ""
    parts: list[str] = []

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, PreformattedString):  # comments, CDATA, ...
                continue
            if isinstance(child, NavigableString):
                parts.append(str(child))
                continue
            if not isinstance(child, Tag):
                continue
            classes = _classes(child)
            if classes & skip:
                continue
            if classes & blocks:
                parts.append(_BREAK)
            elif classes & _SPACED:
                parts.append(" ")
            walk(child)

    walk(element)
    lines = (_clean(line) for line in "".join(parts).split(_BREAK))
    return "\n".join(line for line in lines if line)


def _translation(elements: Iterable[Tag]) -> str:
    return _clean(
        " ".join(
            _text(cn, skip=frozenset()) for el in elements for cn in el.find_all(class_="cn_txt")
        )
    )


def _strip_brackets(text: str) -> str:
    return text.strip().removeprefix("[").removesuffix("]").strip()


def _strip_gloss(text: str) -> str:
    text = text.strip()
    if text.startswith("(=") and text.endswith(")"):
        text = text[2:-1]
    return text.strip()


def _sound_path(anchor: Tag | None) -> str:
    if anchor is None:
        return ""
    href = str(anchor.get("href") or anchor.get("data-src-mp3") or "")
    return href.removeprefix("sound://").lstrip("/")


def _link_texts(elements: Iterable[Tag]) -> tuple[str, ...]:
    return tuple(
        _clean(a.get_text()) for el in elements for a in el.find_all("a") if a.get_text().strip()
    )


def _headword(head: Tag | None) -> str:
    return _text(_first(head, "HWD")) if head is not None else ""


# --- Entry parsing -----------------------------------------------------------------


def _parse_example(element: Tag) -> Example:
    body = element.find(class_="english") or element
    return Example(
        text=_text(body),
        translation=_translation([body]),
        audio=_sound_path(element.find("a", class_="exafile")),
    )


def _examples(element: Tag) -> tuple[Example, ...]:
    return tuple(_parse_example(example) for example in _own(element, {"EXAMPLE"}))


def _english_definition(element: Tag) -> str:
    return _clean(" ".join(_text(d) for d in _own(element, {"DEF"})))


def _parse_pattern(element: Tag) -> Collocation:
    phrase = ""
    for child in element.find_all(True):
        if any(name.startswith("PROPFORM") or name == "COLLO" for name in _classes(child)):
            phrase = _text(child)
            break
    return Collocation(
        phrase=phrase,
        kind="grammar" if "GramExa" in _classes(element) else "collocation",
        gloss=_strip_gloss(_text(_first(element, "GLOSS"))),
        translation=_translation(_own(element, {"DEF"})),
        examples=_examples(element),
    )


def _parse_cross_reference(element: Tag) -> CrossReference | None:
    link = element.find("a", href=True)
    href = str(link["href"]) if link else ""
    if href.startswith("entry://"):
        target = href.removeprefix("entry://").split("#", 1)[0]
    elif href.startswith("#"):  # another homograph on the same page
        target = _text(link.find(class_="REFHWD")) or _text(link)
    else:
        return None  # picture links and other non-entry references
    return CrossReference(text=_text(element).lstrip("→").strip(), target=target)


def _parse_sense(element: Tag) -> Sense:
    lexical = _first(element, "REFHWD") or _first(element, "LEXUNIT")
    labels = tuple(_text(label) for label in _own(element, {"REGISTERLAB", "GEO"}))
    return Sense(
        number=_text(_first(element, "sensenum")),
        signpost=_text(_first(element, "SIGNPOST")),
        lexical_unit=_text(lexical),
        grammar=_strip_brackets(_text(_first(element, "GRAM"))),
        labels=tuple(label for label in labels if label),
        activator=_text(_first(element, "ACTIV")),
        definition=_english_definition(element),
        translation=_translation(_own(element, {"DEF"})),
        synonyms=_link_texts(_own(element, {"SYN"})),
        opposites=_link_texts(_own(element, {"OPP"})),
        related=_link_texts(_own(element, {"RELATEDWD"})),
        examples=_examples(element),
        patterns=tuple(_parse_pattern(p) for p in _own(element, {"GramExa", "ColloExa"})),
        subsenses=tuple(_parse_sense(s) for s in _own(element, {"Subsense", "Sense"})),
        cross_references=tuple(
            ref for ref in map(_parse_cross_reference, _own(element, {"Crossref"})) if ref
        ),
    )


def _parse_pronunciation(head: Tag) -> Pronunciation:
    codes = _first(head, "PronCodes", stop=frozenset({"Inflections"}))
    bre = ame = ""
    if codes is not None:
        bre = _text(codes.find(class_="PRON"))
        ame = _text(codes.find(class_="AMEVARPRON")).removeprefix("$").strip()
    return Pronunciation(
        ipa_bre=bre,
        ipa_ame=ame or bre,
        audio_bre=_sound_path(head.find("a", class_="brefile")),
        audio_ame=_sound_path(head.find("a", class_="amefile")),
    )


def _parse_inflections(head: Tag) -> tuple[str, ...]:
    container = head.find(class_="Inflections")
    if container is None:
        return ()
    forms = []
    for child in container.find_all(True, recursive=False):
        label = child.find(class_="infllab")
        if label is None:
            continue
        form = _text(child, skip=_IGNORED | {"infllab", "neutral"})
        forms.append(f"{_text(label)}: {form}")
    return tuple(forms)


def _parse_run_on(run_on: Tag) -> str:
    """Format a derived form such as ``abandonment noun [uncountable]``."""
    word = _text(_first(run_on, "DERIV"))
    pos = _text(_first(run_on, "lm5pp_POS"))
    grammar = _strip_brackets(_text(_first(run_on, "GRAM")))
    return " ".join(part for part in (word, pos, f"[{grammar}]" if grammar else "") if part)


def _parse_collocation_box(box: Tag) -> list[Collocation]:
    collocations = []
    for section in box.find_all(class_="Section"):
        group = _text(section.find(class_="SECHEADING"))
        for collocate in section.find_all(class_="Collocate"):
            collocations.append(
                Collocation(
                    phrase=_text(collocate.find(class_="COLLOC")),
                    gloss=_strip_gloss(_text(collocate.find(class_="COLLGLOSS"))),
                    translation=_translation(collocate.find_all(class_="DEF")),
                    group=group,
                    examples=tuple(_parse_example(e) for e in collocate.find_all(class_="EXAMPLE")),
                )
            )
    return collocations


def _parse_note(box: Tag) -> Note:
    heading = box.find(class_="lm5ppBoxHead")
    panel = box.find(class_="BoxPanel") or box
    return Note(title=_text(heading), text=_text(panel, blocks=_BOX_BLOCKS))


def _parse_homograph(entry: Tag) -> Homograph:
    head = entry.find(class_="Head")
    senses: list[Sense] = []
    phrasal_verbs: list[Sense] = []
    entry_stop = frozenset({"SpokenSect", "Tail", "lm5ppBox", "Head", "Crossref"})
    for sense in _own(entry, {"Sense"}, entry_stop):
        senses.append(_parse_sense(sense))
    for section in _own(entry, {"SpokenSect"}, entry_stop - {"SpokenSect"}):
        parsed = [_parse_sense(s) for s in _own(section, {"Sense"}, entry_stop)]
        (phrasal_verbs if "PhrasalVerb" in _classes(section) else senses).extend(parsed)

    collocations: list[Collocation] = []
    notes: list[Note] = []
    for box in entry.find_all(class_="lm5ppBox"):
        if "ColloBox" in _classes(box):
            collocations += _parse_collocation_box(box)
        else:
            notes.append(_parse_note(box))

    level = head.find(class_="LEVEL") if head else None
    return Homograph(
        headword=_headword(head),
        homograph=_text(head.find(class_="HOMNUM")) if head else "",
        part_of_speech=_text(_first(head, "lm5pp_POS")) if head else "",
        grammar=_strip_brackets(_text(_first(head, "GRAM", frozenset({"Inflections"}))))
        if head
        else "",
        pronunciation=_parse_pronunciation(head) if head else Pronunciation(),
        inflections=_parse_inflections(head) if head else (),
        frequency=tuple(_text(f) for f in head.find_all(class_="FREQ")) if head else (),
        level=str(level.get("title") or _text(level)) if level else "",
        academic=bool(head and head.find(class_="AC")),
        topics=tuple(_text(topic) for topic in entry.find_all("a", class_="topic")),
        senses=tuple(senses),
        phrasal_verbs=tuple(phrasal_verbs),
        derived_forms=tuple(_parse_run_on(run_on) for run_on in entry.find_all(class_="RunOn")),
        collocations=tuple(collocations),
        notes=tuple(notes),
    )


def _parse_word_family(soup: BeautifulSoup) -> tuple[tuple[str, tuple[str, ...]], ...]:
    family = soup.find(class_="LDOCE_word_family")
    if family is None:
        return ()
    groups: list[tuple[str, list[str]]] = []
    for element in family.find_all(True):
        classes = _classes(element)
        if "pos" in classes:
            groups.append((_text(element), []))
        elif "w" in classes and groups:
            groups[-1][1].append(_text(element))
    return tuple((pos, tuple(words)) for pos, words in groups if words)


def _parse_origin(etym: Tag) -> str:
    body = " ".join(_text(sense) for sense in etym.find_all(class_="Sense", recursive=False))
    return _clean(f"{_headword(etym.find(class_='Head'))} {body}")


def parse_entry_html(html: str, query: str = "") -> DictionaryEntry | None:
    """Parse one LDOCE5++ entry page; return ``None`` if it contains no LDOCE entry."""
    soup = BeautifulSoup(html, "html.parser")
    homographs = tuple(_parse_homograph(entry) for entry in soup.find_all(class_="ldoceEntry"))
    if not homographs:
        return None
    title = soup.find(class_="pagetitle")
    headword = homographs[0].headword or _text(title)
    return DictionaryEntry(
        query=query,
        headword=headword,
        homographs=homographs,
        word_family=_parse_word_family(soup),
        origins=tuple(_parse_origin(etym) for etym in soup.find_all(class_="etym")),
    )


# --- Dictionary facade -------------------------------------------------------------


class LdoceDictionary:
    """Read-only access to an LDOCE5++ ``.mdx`` file and (optionally) its ``.mdd`` resources.

    The first use of each file builds a key index in the user cache directory
    (override with ``cache_dir`` or ``ANKI_EUDIC_CACHE_DIR``); later lookups only
    decompress the blocks they need.
    """

    def __init__(
        self,
        mdx_path: str | Path,
        mdd_path: str | Path | None = None,
        cache_dir: str | Path | None = None,
    ) -> None:
        self._mdx = MdictFile(mdx_path, cache_dir)
        self._mdd = MdictFile(mdd_path, cache_dir) if mdd_path else None

    def lookup(self, word: str) -> DictionaryEntry | None:
        """Return the parsed entry for ``word``, following ``@@@LINK=`` redirects."""
        query = word.strip()
        key = query
        seen: set[str] = set()
        for _ in range(_MAX_REDIRECTS + 1):
            seen.add(key.casefold())
            records = self._mdx.lookup_text(key) or self._mdx.lookup_text(key.replace("’", "'"))
            pages = [r for r in records if not r.lstrip().startswith(_LINK_PREFIX)]
            parsed = [entry for entry in (parse_entry_html(p, query) for p in pages) if entry]
            if parsed:
                entry = parsed[0]
                for extra in parsed[1:]:
                    entry = replace(entry, homographs=entry.homographs + extra.homographs)
                redirected = query if key.casefold() != query.casefold() else ""
                return replace(entry, redirected_from=redirected)
            links = [r.lstrip()[len(_LINK_PREFIX) :].strip() for r in records if r not in pages]
            links = [link for link in links if link and link.casefold() not in seen]
            if not links:
                return None
            key = links[0]
        return None

    def resource(self, path: str) -> bytes | None:
        """Return a ``.mdd`` resource such as ``media/english/breProns/x.mp3``."""
        if self._mdd is None:
            raise RuntimeError("No .mdd file was given to LdoceDictionary")
        key = "\\" + path.removeprefix("sound://").strip().lstrip("/\\").replace("/", "\\")
        records = self._mdd.lookup_raw(key)
        return records[0] if records else None

    def extract_audio(self, path: str, target_dir: str | Path) -> Path | None:
        """Write a ``.mdd`` audio resource into ``target_dir`` and return its path."""
        data = self.resource(path)
        if data is None:
            return None
        target = Path(target_dir).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        destination = target / Path(path.replace("\\", "/")).name
        destination.write_bytes(data)
        return destination

    def close(self) -> None:
        self._mdx.close()
        if self._mdd is not None:
            self._mdd.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
