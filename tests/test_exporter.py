from anki_eudic.exporter import export_anki
from anki_eudic.models import Word


def test_export_writes_anki_headers_and_escaped_fields(tmp_path) -> None:
    destination = tmp_path / "cards"
    count = export_anki(
        [Word("one", explanation="<unsafe>\nsecond", context="a\tb", star=1)],
        destination,
        "My Deck",
    )

    assert count == 1
    content = (tmp_path / "cards.tsv").read_text(encoding="utf-8")
    assert "#separator:Tab\n#html:true\n#deck:My Deck" in content
    assert "&lt;unsafe&gt;<br>second" in content
    assert "a    b" in content
    assert "a\tb" not in content
