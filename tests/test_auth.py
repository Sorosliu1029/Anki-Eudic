import pytest

from anki_eudic.auth import normalize_token


def test_normalize_token_adds_scheme() -> None:
    assert normalize_token(" secret ") == "NIS secret"


def test_normalize_token_preserves_scheme_case_insensitively() -> None:
    assert normalize_token("nis secret") == "nis secret"


def test_normalize_token_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match="empty"):
        normalize_token("  ")
