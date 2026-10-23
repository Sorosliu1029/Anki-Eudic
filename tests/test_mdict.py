import pytest
from mdict_builder import build_mdict

from anki_eudic.mdict import MdictFile, ripemd128


def test_ripemd128_matches_reference_vectors() -> None:
    assert ripemd128(b"").hex() == "cdf26213a150dc3ecb610f18f6b38b46"
    assert ripemd128(b"abc").hex() == "c14a12199c66e4ba84636b0f69144c77"
    assert ripemd128(b"message digest").hex() == "9e327b3d6e523062afc1132d7df9d1b8"
    assert ripemd128(b"1234567890" * 8).hex() == "3f45ef194732c2dbb2c4a2c769795fa3"


@pytest.mark.parametrize("encrypted", [True, False])
def test_mdx_lookup_reads_records_across_blocks(tmp_path, encrypted: bool) -> None:
    entries = [
        ("alpha", b"<p>first</p>\x00"),
        ("Beta", b"<p>second record that is a bit longer</p>\x00"),
        ("gamma", b"@@@LINK=alpha\r\n\x00"),
        ("zeta", "<p>café</p>\x00".encode()),
    ]
    path = build_mdict(tmp_path / "test.mdx", entries, encrypted=encrypted)

    mdx = MdictFile(path, cache_dir=tmp_path / "cache")

    assert len(mdx) == 4
    assert mdx.header["Title"] == "Test & Demo"
    assert mdx.lookup_text("alpha") == ["<p>first</p>"]
    assert mdx.lookup_text("beta") == ["<p>second record that is a bit longer</p>"]
    assert mdx.lookup_text("ZETA") == ["<p>café</p>"]
    assert mdx.lookup_text("gamma") == ["@@@LINK=alpha\r\n"]
    assert mdx.lookup_text("missing") == []
    assert mdx.keys("") == ["alpha", "Beta", "gamma", "zeta"]
    mdx.close()


def test_index_is_cached_and_reused(tmp_path) -> None:
    path = build_mdict(tmp_path / "test.mdx", [("a", b"1\x00"), ("b", b"2\x00")])
    cache = tmp_path / "cache"

    MdictFile(path, cache_dir=cache).close()
    indexes = list(cache.glob("*.sqlite3"))
    again = MdictFile(path, cache_dir=cache)

    assert len(indexes) == 1
    assert again.lookup_text("b") == ["2"]
    assert list(cache.glob("*.sqlite3")) == indexes


def test_mdd_uses_utf16_keys_and_returns_bytes(tmp_path) -> None:
    entries = [
        ("\\media\\a.mp3", b"ID3audio-a"),
        ("\\media\\b.mp3", b"ID3audio-b"),
        ("\\style.css", b"body{}"),
    ]
    path = build_mdict(tmp_path / "test.mdd", entries, mdd=True)

    mdd = MdictFile(path, cache_dir=tmp_path / "cache")

    assert mdd.lookup_raw("\\media\\b.mp3") == [b"ID3audio-b"]
    assert mdd.lookup_raw("\\MEDIA\\A.MP3") == [b"ID3audio-a"]
    assert mdd.keys("\\media") == ["\\media\\a.mp3", "\\media\\b.mp3"]


def test_missing_file_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        MdictFile(tmp_path / "nope.mdx", cache_dir=tmp_path)
