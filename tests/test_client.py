import httpx
import pytest

from anki_eudic.client import EudicClient, EudicError


def test_categories_are_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "NIS test"
        assert request.url.params["language"] == "en"
        return httpx.Response(200, json={"data": [{"id": 0, "name": "Unknown", "language": "en"}]})

    with EudicClient("NIS test", transport=httpx.MockTransport(handler)) as client:
        result = client.categories()
    assert result[0].id == "0"
    assert result[0].name == "Unknown"


def test_words_paginate_and_deduplicate() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        rows = {
            0: [
                {"word": "Action", "phon": "/a/", "exp": "act", "star": 2},
                {"word": "amplify", "context_line": "Please amplify it."},
            ],
            1: [{"word": "action", "exp": "duplicate"}],
        }[page]
        return httpx.Response(200, json={"data": rows})

    with EudicClient("NIS test", transport=httpx.MockTransport(handler)) as client:
        result = client.words("0", page_size=2)
    assert [item.word for item in result] == ["Action", "amplify"]
    assert result[0].star == 2
    assert result[1].context == "Please amplify it."


def test_auth_error_is_friendly() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(401, json={"message": "no"}))
    with EudicClient("NIS bad", transport=transport) as client:
        with pytest.raises(EudicError, match="invalid or expired token"):
            client.categories()
