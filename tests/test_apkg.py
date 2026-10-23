import json
import os
import sqlite3
import zipfile
from pathlib import Path

import pytest

from anki_eudic.apkg import (
    FIELDS,
    MODEL_ID,
    deck_id,
    export_apkg,
    media_name,
    note_guid,
    render_entry,
)
from anki_eudic.dictionary import (
    DictionaryEntry,
    Example,
    Homograph,
    Pronunciation,
    Sense,
)
from anki_eudic.models import Word

BRE = "media/english/breProns/zorble0101.mp3"
AME = "media/english/ameProns/zorble.mp3"

ZORBLE = DictionaryEntry(
    query="zorble",
    headword="zorble",
    homographs=(
        Homograph(
            headword="zorble",
            part_of_speech="verb",
            pronunciation=Pronunciation("ˈzɔːbəl", "ˈzɔːrbəl", BRE, AME),
            senses=(
                Sense(
                    number="1",
                    signpost="MOVE",
                    grammar="[intransitive]",
                    definition="to roll <downhill> in a ball",
                    translation="滚下山",
                    examples=(
                        Example("We zorbled all afternoon.", "我们滚了一下午。", "media/x.mp3"),
                        Example("Second example."),
                        Example("Third example is dropped."),
                    ),
                ),
                Sense(number="2", subsenses=(Sense(number="a", definition="a subsense"),)),
            ),
        ),
    ),
    origins=("zorble (2000s) invented",),
)


class FakeDictionary:
    def __init__(self, entries: dict[str, DictionaryEntry], resources: dict[str, bytes]) -> None:
        self.entries = entries
        self.resources = resources

    def lookup(self, word: str) -> DictionaryEntry | None:
        return self.entries.get(word.casefold())

    def resource(self, path: str) -> bytes | None:
        return self.resources.get(path)


def read_package(path: Path) -> tuple[list[tuple[str, dict[str, str]]], dict[str, str], dict]:
    with zipfile.ZipFile(path) as archive:
        media = json.loads(archive.read("media"))
        names = {name: archive.read(index).decode("latin-1") for index, name in media.items()}
        database = path.parent / "collection.anki2"
        database.write_bytes(archive.read("collection.anki2"))
    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT guid, flds FROM notes ORDER BY id").fetchall()
        models = json.loads(connection.execute("SELECT models FROM col").fetchone()[0])
    notes = [(guid, dict(zip(FIELDS, flds.split("\x1f")))) for guid, flds in rows]
    return notes, names, models


def test_guid_ignores_case_and_content() -> None:
    assert note_guid("Hello ") == note_guid("hello")
    assert note_guid("hello") != note_guid("help")


def test_deck_id_is_stable_per_name() -> None:
    assert deck_id("Eudic") == deck_id("Eudic")
    assert deck_id("Eudic") != deck_id("Eudic::Unknown")
    assert 0 < deck_id("Eudic") < 1 << 63


def test_media_name_is_ascii_and_keeps_accent_directory() -> None:
    assert media_name(BRE) == "ldoce_breProns_zorble0101.mp3"
    assert media_name(AME) == "ldoce_ameProns_zorble.mp3"
    assert media_name("media\\english\\breProns\\café's.mp3") == "ldoce_breProns_caf_s.mp3"


def test_render_entry_escapes_and_limits_examples() -> None:
    fields = render_entry(ZORBLE)

    assert fields["PhoneticUK"] == "/ˈzɔːbəl/"
    assert fields["PhoneticUS"] == "/ˈzɔːrbəl/"
    assert fields["PartOfSpeech"] == "verb"
    definition = fields["Definition"]
    assert "to roll &lt;downhill&gt; in a ball" in definition
    assert "MOVE" in definition
    assert (
        '<span class="reveal"><span class="def en">to roll &lt;downhill&gt; in a ball</span> '
        '<span class="tran">滚下山</span></span>'
    ) in definition
    assert "Second example." in definition
    assert "Third example" not in definition
    assert '<span class="example en">We zorbled all afternoon.</span>' in definition
    assert '<li><span class="example">Second example.</span></li>' in definition
    assert "a subsense" in definition
    assert definition.count("[intransitive]") == 1
    assert "invented" in fields["Extra"]


def test_export_without_dictionary_uses_eudic_fields(tmp_path: Path) -> None:
    summary = export_apkg(
        [Word("one", phonetic="wʌn", explanation="<b>num.</b>\n一", context="a\tb", star=2)],
        tmp_path / "cards.txt",
        "My Deck",
    )

    assert summary.path == tmp_path / "cards.apkg"
    assert (summary.notes, summary.enriched, summary.audio) == (1, 0, 0)
    notes, media, models = read_package(summary.path)
    guid, fields = notes[0]
    assert guid == note_guid("one")
    assert fields["PhoneticUK"] == "/wʌn/" and fields["PhoneticUS"] == ""
    assert fields["Explanation"] == "&lt;b&gt;num.&lt;/b&gt;<br>一"
    assert fields["Context"] == "a    b"
    assert fields["Star"] == "2"
    assert fields["Definition"] == "" and media == {}
    assert list(models) == [str(MODEL_ID)]
    assert [field["name"] for field in models[str(MODEL_ID)]["flds"]] == list(FIELDS)


def test_export_with_dictionary_bundles_audio(tmp_path: Path) -> None:
    dictionary = FakeDictionary({"zorble": ZORBLE}, {BRE: b"uk-mp3", AME: b"us-mp3"})

    summary = export_apkg(
        [
            Word("Zorble", phonetic="ignored", explanation="eudic", context="ctx"),
            Word("missing", phonetic="mɪsɪŋ", explanation="eudic"),
        ],
        tmp_path / "out.apkg",
        dictionary=dictionary,
    )

    assert (summary.notes, summary.enriched, summary.audio) == (2, 1, 2)
    notes, media, _ = read_package(summary.path)
    zorble, missing = (fields for _, fields in notes)
    assert zorble["AudioUK"] == "[sound:ldoce_breProns_zorble0101.mp3]"
    assert zorble["AudioUS"] == "[sound:ldoce_ameProns_zorble.mp3]"
    assert zorble["PhoneticUK"] == "/ˈzɔːbəl/"
    assert zorble["Explanation"] == "" and zorble["Context"] == "ctx"
    assert missing["PhoneticUK"] == "/mɪsɪŋ/" and missing["AudioUK"] == ""
    assert missing["Explanation"] == "eudic"
    assert media == {
        "ldoce_breProns_zorble0101.mp3": "uk-mp3",
        "ldoce_ameProns_zorble.mp3": "us-mp3",
    }


def test_missing_audio_resource_leaves_field_empty(tmp_path: Path) -> None:
    dictionary = FakeDictionary({"zorble": ZORBLE}, {BRE: b"uk-mp3"})

    summary = export_apkg([Word("zorble")], tmp_path / "out.apkg", dictionary=dictionary)

    notes, media, _ = read_package(summary.path)
    assert notes[0][1]["AudioUS"] == "" and list(media) == ["ldoce_breProns_zorble0101.mp3"]


def test_reexport_updates_notes_in_anki(tmp_path: Path) -> None:
    anki = pytest.importorskip("anki.collection")
    from anki.import_export_pb2 import ImportAnkiPackageOptions, ImportAnkiPackageRequest

    collection = anki.Collection(str(tmp_path / "collection.anki2"))

    def import_package(path: Path) -> None:
        options = ImportAnkiPackageOptions(with_scheduling=False)
        collection.import_anki_package(
            ImportAnkiPackageRequest(package_path=str(path), options=options)
        )

    try:
        import_package(export_apkg([Word("one", context="v1")], tmp_path / "a.apkg").path)
        # genanki stamps notes with whole seconds; make the imported note look older.
        collection.db.execute("UPDATE notes SET mod = mod - 10")
        import_package(export_apkg([Word("ONE", context="v2")], tmp_path / "b.apkg").path)

        note_ids = collection.find_notes("")
        assert len(note_ids) == 1
        assert collection.get_note(note_ids[0])["Context"] == "v2"
    finally:
        collection.close()


LDOCE = Path(os.environ.get("LDOCE_DIR", "~/Library/Eudb_en")).expanduser()
MDX = LDOCE / "LDOCE5++ V 1-35.mdx"


@pytest.mark.skipif(not MDX.exists(), reason="LDOCE5++ dictionary files not available")
def test_export_with_real_dictionary(tmp_path: Path) -> None:
    from anki_eudic.dictionary import LdoceDictionary

    with LdoceDictionary(MDX, MDX.with_suffix(".mdd")) as ldoce:
        summary = export_apkg([Word("pronounce")], tmp_path / "real.apkg", dictionary=ldoce)

    notes, media, _ = read_package(summary.path)
    fields = notes[0][1]
    assert summary.enriched == 1 and summary.audio == 2
    assert fields["PhoneticUK"] == fields["PhoneticUS"] == "/prəˈnaʊns/"
    assert "How do you pronounce your name?" in fields["Definition"]
    assert fields["AudioUK"] == "[sound:ldoce_breProns_pronounce0205.mp3]"
    assert set(media) == {"ldoce_breProns_pronounce0205.mp3", "ldoce_ameProns_pronounce.mp3"}


def test_export_without_audio_skips_resources(tmp_path: Path) -> None:
    class NoResources(FakeDictionary):
        def resource(self, path: str) -> bytes | None:
            raise RuntimeError("No .mdd file was given to LdoceDictionary")

    dictionary = NoResources({"zorble": ZORBLE}, {})

    summary = export_apkg([Word("zorble")], tmp_path / "out", dictionary=dictionary, audio=False)

    notes, media, _ = read_package(summary.path)
    assert summary.enriched == 1 and media == {}
    assert notes[0][1]["AudioUK"] == "" and "滚下山" in notes[0][1]["Definition"]
