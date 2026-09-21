"""Small client for the Eudic study-list API documented in this repository."""

from __future__ import annotations

from typing import Any

import httpx

from .models import Category, Word

BASE_URL = "https://api.frdic.com/api/open/v1"


class EudicError(RuntimeError):
    """A friendly representation of an API or network failure."""


class EudicClient:
    def __init__(self, token: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": token, "User-Agent": "Anki-Eudic/0.1"},
            timeout=20,
            transport=transport,
        )

    def __enter__(self) -> EudicClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            detail = (
                "invalid or expired token"
                if exc.response.status_code in (401, 403)
                else "API error"
            )
            raise EudicError(f"Eudic returned {exc.response.status_code} ({detail}).") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise EudicError(f"Could not read Eudic's response: {exc}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            message = (
                payload.get("message", "unexpected response")
                if isinstance(payload, dict)
                else "unexpected response"
            )
            raise EudicError(f"Eudic did not return a list: {message}")
        return data

    def categories(self, language: str = "en") -> list[Category]:
        rows = self._get("/studylist/category", {"language": language})
        return [
            Category(id=str(row["id"]), name=str(row["name"]), language=str(row["language"]))
            for row in rows
        ]

    def words(self, category_id: str, language: str = "en", *, page_size: int = 100) -> list[Word]:
        """Fetch every page in a study list and de-duplicate by spelling."""
        if not 1 <= page_size <= 100:
            raise ValueError("page_size must be between 1 and 100")
        result: list[Word] = []
        seen: set[str] = set()
        for page in range(10_000):
            rows = self._get(
                "/studylist/words",
                {
                    "language": language,
                    "category_id": category_id,
                    "page": page,
                    "page_size": page_size,
                },
            )
            for row in rows:
                spelling = str(row.get("word", "")).strip()
                key = spelling.casefold()
                if not spelling or key in seen:
                    continue
                seen.add(key)
                result.append(
                    Word(
                        word=spelling,
                        phonetic=str(row.get("phon") or ""),
                        explanation=str(row.get("exp") or ""),
                        context=str(row.get("context_line") or ""),
                        added_at=str(row.get("add_time") or ""),
                        star=int(row.get("star") or 0),
                    )
                )
            if len(rows) < page_size:
                return result
        raise EudicError("Pagination limit reached; export was stopped for safety.")
