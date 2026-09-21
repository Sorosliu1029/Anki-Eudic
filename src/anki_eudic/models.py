"""Domain objects returned by the Eudic API."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Category:
    id: str
    name: str
    language: str


@dataclass(frozen=True, slots=True)
class Word:
    word: str
    phonetic: str = ""
    explanation: str = ""
    context: str = ""
    added_at: str = ""
    star: int = 0
