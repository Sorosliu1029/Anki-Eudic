"""Tests for the LDOCE5++ entry parser and dictionary facade.

The HTML below is hand-written for an invented word. It only mimics the class names
and nesting used by LDOCE5++ entries; it contains no dictionary content.
"""

import os
from pathlib import Path

import pytest
from mdict_builder import build_mdict

from anki_eudic.dictionary import CrossReference, LdoceDictionary, parse_entry_html

ENTRY_HTML = """
<link href="LM5style.css" rel="stylesheet" type="text/css" />
<span class="lm5ppbody"><div class="entry_content"><h1 class="pagetitle">zorble</h1>
<div class="dictionary">
<div class="wordfams"><span class="LDOCE5pp_sensefold foldsign_fold">
<span class="asset_intro">Word family</span></span><span class="LDOCE_word_family">
<span class="pos">noun</span><span class="w" title="zorble">zorble</span>
<a class="crossRef w" href="entry://zorbler">zorbler</a>
<span class="pos">adjective</span>
<span class="pos">verb</span><span class="w" title="zorble">zorble</span></span></div>
<span class="dictentry"><span class="dictionary_intro span">
<span class="en_title">Longman</span></span><span class="dictlink">
<span class="ldoceEntry Entry" id="zorble__entry_0">
<div class="topics_container"><span class="related_topics">Related topics: </span>
<a class="topic" href="entry://Games-topic">Games</a><span class="comma">, </span>
<a class="topic" href="entry://Sound-topic">Sound</a></div><!-- comment -->
<span class="frequent Head"><span class="HWD">zor<span class="HYP"><span class="HYP">·</span></span>ble</span>
<span class="HOMNUM">1</span>
<a class="PronCodes" href="sound://media/english/ameProns/zorble1.mp3">
<span class="neutral span"> /</span><span class="PRON">ˈzɔːbəl</span>
<span class="AMEVARPRON"><span class="neutral span"> $ </span>ˈzɔːr<span class="i">ə</span>l</span>
<span class="neutral span">/</span></a>
<span class="tooltip LEVEL" title="Core vocabulary: High-frequency"> ●●●</span>
<span class="FREQ" title="Top 3000 spoken words">S3</span>
<span class="FREQ" title="Top 2000 written words">W2</span>
<span class="AC" title="Academic Word list">AWL</span>
<span class="lm5pp_POS"> verb</span>
<span class="Inflections"><span class="neutral span">(</span>
<span class="PASTTENSE"><span class="infllab span">past tense</span> zorbled</span>
<span class="PronCodes"><span class="PRON">zɔːbəld</span></span>
<span class="PRESPART"><span class="neutral span">, </span>
<span class="infllab span">present participle</span> zorbling</span>
<span class="neutral span">)</span></span>
<a class="speaker brefile fa fa-volume-up" href="sound://media/english/breProns/zorble0205.mp3"> </a>
<a class="speaker amefile fa fa-volume-up" href="sound://media/english/ameProns/zorble1.mp3"> </a>
</span>
<span class="newline Sense" id="zorble__1"><span class="LDOCE5pp_sensefold">
<span class="sensenum span">1</span><span class="foldsign"><span class="foldblank"> </span></span></span>
<span class="SIGNPOST LDOCE5pp_sensefold_other">make a noise<span class="cn_txt">发声</span></span>
<span class="Subsense"><span class="sensenum span">a)</span>
<span class="GRAM LDOCE_switch_lang switch_siblings"><span class="neutral span">[</span>intransitive<span class="neutral span">]</span></span>
<span class="DEF LDOCE_switch_lang switch_siblings"> to make a low <a class="defRef" href="entry://humming">humming</a> sound</span>
<span class="DEF LDOCE_switch_lang switch_siblings"> <span class="cn_txt"> 发出嗡嗡声</span></span>
<span class="EXAMPLE"><a class="speaker exafile fa fa-volume-up" href="sound://media/english/exaProns/zx-001.mp3"> </a>
<span class="english LDOCE_switch_lang switch_children">The old fridge zorbled all night.<span class="cn_txt"> 旧冰箱整夜嗡嗡响。</span></span></span>
<span class="GramExa"><span class="PROPFORMPREP">zorble at somebody</span>
<span class="EXAMPLE"><a class="speaker exafile fa fa-volume-up" href="sound://media/english/exaProns/zx-002.mp3"> </a>
<span class="english LDOCE_switch_lang switch_children">The cat zorbled at me.</span></span></span>
</span>
<span class="Subsense"><span class="sensenum span">b)</span>
<span class="GRAM LDOCE_switch_lang switch_siblings">[transitive]</span>
<span class="DEF LDOCE_switch_lang switch_siblings">to say something in a low voice</span>
<span class="Thesref"><span class="thesref span">►see thesaurus at</span><a class="crossRef" href="entry://hum"><span class="REFHWD">hum</span></a></span></span>
</span>
<span class="newline Sense" id="zorble__2"><span class="LDOCE5pp_sensefold">
<span class="sensenum span">2</span></span>
<span class="REFHWD merge_sense LDOCE5pp_sensefold_other">zorble along</span>
<span class="REGISTERLAB LDOCE_switch_lang switch_siblings"> informal</span>
<span class="GEO LDOCE_switch_lang">British English</span>
<span class="ACTIV">MOVE</span>
<span class="FIELD">DSO</span>
<span class="DEF LDOCE_switch_lang switch_siblings"> to move slowly and noisily</span>
<span class="SYN"><span class="synopp span">SYN</span><a href="entry://trundle">trundle</a></span>
<span class="OPP"><span class="synopp span">OPP</span><a href="entry://zoom">zoom</a></span>
<span class="RELATEDWD"><span class="neutral span"> → </span><a href="entry://zorbler">zorbler</a></span>
<span class="ColloExa"><span class="COLLO">zorble to a halt</span>
<span class="GLOSS"><span class="neutral span"> (=</span>stop slowly<span class="neutral span">)</span></span>
<span class="EXAMPLE"><span class="english">The van zorbled to a halt.</span></span></span>
<span class="Crossref"><span class="REFLEX">See picture of</span><a class="crossRef" href="javascript:void(0);"><span class="REFHWD">zorble</span></a></span>
<span class="ThesBox BoxHide lm5ppBox"><span class="heading span lm5ppBoxHead">
<span class="foldsign"><span class="foldblank"> </span></span>THESAURUS</span>
<span class="BoxPanel"><span class="Section"><span class="Exponent">
<span class="display EXP">zorble</span><span class="DEF">to hum quietly</span>
<span class="EXAMPLE"><span class="english">It zorbles.</span></span></span></span></span></span>
</span>
<span class="SpokenSect PhrasalVerb"><span class="spokensectheader span">PHRASAL VERBS</span>
<span class="newline Sense" id="zorble__phr__1"><span class="sensenum span">3</span>
<span class="REFHWD merge_sense">zorble on <span class="OBJECT">about something</span></span>
<span class="lm5pp_POS">phrasal verb</span>
<span class="DEF LDOCE_switch_lang switch_siblings">to talk for too long</span>
<span class="EXAMPLE"><span class="english">He zorbled on for hours.</span></span></span></span>
<span class="Tail"><span class="RunOn"><span class="neutral span">—</span>
<span class="DERIV">zorbling</span><span class="lm5pp_POS"> noun</span>
<span class="GRAM"><span class="neutral span">[</span>uncountable<span class="neutral span">]</span></span></span></span>
</span></span>
<span class="asset div corpus"><span class="asset_intro">Examples from the Corpus</span></span>
<span class="assetlink corpus"><span class="exa">• A corpus line that should be ignored.</span></span>
</span>
<span class="dictentry"><span class="dictlink"><span class="ldoceEntry Entry" id="zorble__8">
<span class="Head"><span class="HWD">zorble</span><span class="HOMNUM">2</span>
<span class="lm5pp_POS"> noun</span>
<span class="GRAM"><span class="neutral span">[</span>countable<span class="neutral span">]</span></span>
<a class="speaker brefile fa fa-volume-up" href="sound://media/english/breProns/zorble0205.mp3"> </a>
</span>
<span class="Sense" id="zorble__9"><span class="DEF">a low humming sound</span>
<span class="ColloBox BoxHide lm5ppBox"><span class="heading span lm5ppBoxHead">COLLOCATIONS</span>
<span class="BoxPanel"><span class="Section"><span class="SECHEADING"><span>adjectives</span></span>
<span class="Collocate"><span class="collo COLLOC">a faint zorble</span>
<span class="COLLGLOSS"><span class="neutral span">(=</span>a quiet one<span class="neutral span">)</span></span>
<span class="EXAMPLE"><span class="english">I heard a faint zorble.</span></span></span>
<span class="Collocate"><span class="collo COLLOC">a loud zorble</span></span></span>
</span></span>
<span class="GramBox lm5ppBox"><span class="HEADING lm5ppBoxHead"><span class="boxheader span">GRAMMAR: Plural</span></span>
<span class="BoxPanel"><span class="EXPL"><span>The plural is</span> <span class="EXPR">zorbles</span>.</span>
<span class="EXAMPLE">Two zorbles.</span></span></span>
</span></span></span></span>
<span class="dictentry bussdict"><span class="dictlink"><span class="bussdictEntry Entry">
<span class="Head"><span class="HWD">zorble</span></span>
<span class="Sense"><span class="DEF">business sense that is skipped</span></span>
</span></span></span>
<span class="etym"><span class="asset_intro">Origin</span> <span class="Head"><span class="HWD">zorble</span>
<span class="HOMNUM">1</span></span> <span class="Sense"><span class="CENTURY"><span class="neutral span">(</span>1900-2000<span class="neutral span">)</span></span> <span class="LANG">Invented</span>
<span class="ORIGIN">zorb</span></span></span>
</div><div class="lm5pp_popup"><span class="lm5pp_POS">verb</span></div></div></span>
"""


@pytest.fixture(scope="module")
def entry():
    return parse_entry_html(ENTRY_HTML, query="Zorble")


def test_parses_headword_homographs_and_parts_of_speech(entry) -> None:
    assert entry.query == "Zorble"
    assert entry.headword == "zorble"
    assert [h.homograph for h in entry.homographs] == ["1", "2"]
    assert entry.parts_of_speech == ("verb", "noun")
    first = entry.homographs[0]
    assert first.topics == ("Games", "Sound")
    assert first.inflections == ("past tense: zorbled", "present participle: zorbling")
    assert first.derived_forms == ("zorbling noun [uncountable]",)


def test_parses_pronunciation_and_frequency_markers(entry) -> None:
    head = entry.homographs[0]
    assert head.pronunciation.ipa_bre == "ˈzɔːbəl"
    assert head.pronunciation.ipa_ame == "ˈzɔːrəl"
    assert head.pronunciation.audio_bre == "media/english/breProns/zorble0205.mp3"
    assert head.pronunciation.audio_ame == "media/english/ameProns/zorble1.mp3"
    assert head.level == "Core vocabulary: High-frequency"
    assert head.frequency == ("S3", "W2")
    assert head.academic is True
    assert entry.pronunciation == head.pronunciation


def test_ame_ipa_defaults_to_shared_pronunciation_and_missing_ipa_is_empty(entry) -> None:
    noun = entry.homographs[1]
    assert noun.pronunciation.ipa_bre == ""
    assert noun.pronunciation.audio_bre == "media/english/breProns/zorble0205.mp3"
    assert noun.pronunciation.audio_ame == ""
    assert noun.grammar == "countable"
    assert noun.frequency == ()
    assert noun.academic is False


def test_parses_senses_subsenses_and_examples(entry) -> None:
    first, second = entry.homographs[0].senses
    assert first.number == "1"
    assert first.signpost == "make a noise"
    assert first.definition == ""
    sub_a, sub_b = first.subsenses
    assert sub_a.number == "a)"
    assert sub_a.grammar == "intransitive"
    assert sub_a.definition == "to make a low humming sound"
    assert sub_a.translation == "发出嗡嗡声"
    assert sub_a.examples[0].text == "The old fridge zorbled all night."
    assert sub_a.examples[0].translation == "旧冰箱整夜嗡嗡响。"
    assert sub_a.examples[0].audio == "media/english/exaProns/zx-001.mp3"
    pattern = sub_a.patterns[0]
    assert (pattern.phrase, pattern.kind) == ("zorble at somebody", "grammar")
    assert pattern.examples[0].text == "The cat zorbled at me."
    assert sub_b.grammar == "transitive"
    assert sub_b.lexical_unit == ""
    assert sub_b.examples == ()

    assert second.lexical_unit == "zorble along"
    assert second.labels == ("informal", "British English")
    assert second.activator == "MOVE"
    assert second.definition == "to move slowly and noisily"
    assert second.synonyms == ("trundle",)
    assert second.opposites == ("zoom",)
    assert second.related == ("zorbler",)
    collocation = second.patterns[0]
    assert (collocation.phrase, collocation.kind, collocation.gloss) == (
        "zorble to a halt",
        "collocation",
        "stop slowly",
    )
    assert collocation.examples[0].text == "The van zorbled to a halt."
    assert second.examples == ()
    assert second.cross_references == ()


def test_parses_phrasal_verbs_boxes_word_family_and_origin(entry) -> None:
    verb, noun = entry.homographs
    (phrasal,) = verb.phrasal_verbs
    assert phrasal.lexical_unit == "zorble on about something"
    assert phrasal.definition == "to talk for too long"
    assert phrasal.examples[0].text == "He zorbled on for hours."

    assert [note.title for note in verb.notes] == ["THESAURUS"]
    assert "zorble" in verb.notes[0].text and "It zorbles." in verb.notes[0].text
    assert [note.title for note in noun.notes] == ["GRAMMAR: Plural"]
    assert noun.notes[0].text == "The plural is zorbles.\nTwo zorbles."

    first, second = noun.collocations
    assert (first.phrase, first.group, first.gloss) == (
        "a faint zorble",
        "adjectives",
        "a quiet one",
    )
    assert first.examples[0].text == "I heard a faint zorble."
    assert second.phrase == "a loud zorble"

    assert entry.word_family == (("noun", ("zorble", "zorbler")), ("verb", ("zorble",)))
    assert entry.origins == ("zorble (1900-2000) Invented zorb",)


def test_skips_business_dictionary_and_corpus(entry) -> None:
    assert len(entry.homographs) == 2
    texts = repr(entry)
    assert "business sense" not in texts
    assert "corpus line" not in texts


def test_audio_paths_lists_unique_resources(entry) -> None:
    assert entry.audio_paths() == (
        "media/english/breProns/zorble0205.mp3",
        "media/english/ameProns/zorble1.mp3",
        "media/english/exaProns/zx-001.mp3",
        "media/english/exaProns/zx-002.mp3",
    )


def test_parses_cross_reference_only_senses() -> None:
    html = (
        '<span class="ldoceEntry Entry"><span class="Head"><span class="HWD">zorbs</span></span>'
        '<span class="Sense"><span class="sensenum">1</span><span class="Crossref">'
        '<span class="neutral span">→ </span><span class="REFLEX">plural of zorb</span>'
        '<a class="crossRef" href="entry://zorb#zorb__3__a"><span class="REFHWD">'
        '<span class="neutral span"> at </span>zorb</span><span class="REFHOMNUM">2</span></a>'
        '</span></span><span class="Sense"><span class="Crossref">→ '
        '<a class="crossRef" href="#zorbs__3"><span class="REFHWD">Zorbs.</span></a>'
        "</span></span></span>"
    )
    sense, local = parse_entry_html(html).homographs[0].senses
    assert sense.number == "1"
    assert sense.cross_references == (CrossReference("plural of zorb at zorb2", "zorb"),)
    assert local.cross_references == (CrossReference("Zorbs.", "Zorbs."),)


def test_returns_none_for_html_without_entries() -> None:
    assert parse_entry_html("<p>nothing</p>") is None


@pytest.fixture
def tiny_dictionary(tmp_path):
    def page(word: str) -> bytes:
        return (
            f'<span class="ldoceEntry Entry"><span class="Head"><span class="HWD">{word}</span>'
            '<span class="lm5pp_POS">noun</span></span>'
            f'<span class="Sense"><span class="DEF">a test word {word}</span></span></span>\x00'
        ).encode()

    mdx = build_mdict(
        tmp_path / "t.mdx",
        [
            ("alpha", page("alpha")),
            ("alphas", b"@@@LINK=alpha\r\n\x00"),
            ("beta", page("beta")),
            ("loop", b"@@@LINK=loop\r\n\x00"),
        ],
    )
    mdd = build_mdict(
        tmp_path / "t.mdd",
        [("\\media\\english\\breProns\\alpha.mp3", b"ID3fake-mp3")],
        mdd=True,
    )
    dictionary = LdoceDictionary(mdx, mdd, cache_dir=tmp_path / "cache")
    yield dictionary
    dictionary.close()


def test_lookup_follows_links_and_ignores_case(tiny_dictionary) -> None:
    entry = tiny_dictionary.lookup("Alphas")
    assert entry is not None
    assert entry.headword == "alpha"
    assert entry.redirected_from == "Alphas"
    assert entry.homographs[0].senses[0].definition == "a test word alpha"
    assert tiny_dictionary.lookup("  BETA ").redirected_from == ""
    assert tiny_dictionary.lookup("missing") is None
    assert tiny_dictionary.lookup("loop") is None


def test_extract_audio_writes_resource_file(tiny_dictionary, tmp_path) -> None:
    target = tmp_path / "out"
    path = tiny_dictionary.extract_audio("media/english/breProns/alpha.mp3", target)
    assert path == target / "alpha.mp3"
    assert path.read_bytes() == b"ID3fake-mp3"
    assert tiny_dictionary.resource("sound://media/english/breProns/alpha.mp3") == b"ID3fake-mp3"
    assert tiny_dictionary.extract_audio("media/missing.mp3", target) is None


def test_extract_audio_requires_mdd(tmp_path) -> None:
    mdx = build_mdict(tmp_path / "t.mdx", [("a", b"x\x00")])
    with (
        LdoceDictionary(mdx, cache_dir=tmp_path / "cache") as dictionary,
        pytest.raises(RuntimeError),
    ):
        dictionary.resource("media/a.mp3")


LDOCE_DIR = Path(os.environ.get("LDOCE_DIR", "~/Library/Eudb_en")).expanduser()
REAL_MDX = LDOCE_DIR / "LDOCE5++ V 1-35.mdx"
REAL_MDD = LDOCE_DIR / "LDOCE5++ V 1-35.mdd"


@pytest.mark.skipif(not REAL_MDX.exists(), reason="LDOCE5++ dictionary files not installed")
def test_real_ldoce_dictionary(tmp_path) -> None:
    with LdoceDictionary(REAL_MDX, REAL_MDD if REAL_MDD.exists() else None) as dictionary:
        entry = dictionary.lookup("pronounce")
        assert entry is not None
        assert entry.headword == "pronounce"
        assert "verb" in entry.parts_of_speech
        assert entry.pronunciation.ipa_bre
        senses = entry.homographs[0].senses
        assert len(senses) >= 3
        assert all(sense.definition or sense.subsenses for sense in senses)
        assert any(sense.examples for sense in senses)
        assert dictionary.lookup("ran").headword == "ran"
        assert dictionary.lookup("abandonment").redirected_from == "abandonment"
        if REAL_MDD.exists():
            audio = dictionary.extract_audio(entry.pronunciation.audio_bre, tmp_path)
            assert audio is not None
            assert audio.read_bytes()[:2] in {b"ID", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}
