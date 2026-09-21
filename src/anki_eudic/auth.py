"""Credential handling that never writes the Eudic token to project files."""

from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError

SERVICE = "anki-eudic"
USERNAME = "eudic-api-token"
ENV_VAR = "EUDIC_TOKEN"


class CredentialError(RuntimeError):
    """Raised when the system credential store cannot be used."""


def normalize_token(token: str) -> str:
    """Return the authorization value expected by Eudic."""
    value = token.strip()
    if not value:
        raise ValueError("The token cannot be empty.")
    return value if value.upper().startswith("NIS ") else f"NIS {value}"


def load_token() -> str | None:
    """Load from the environment first, then the operating-system keyring."""
    if token := os.getenv(ENV_VAR):
        return normalize_token(token)
    try:
        token = keyring.get_password(SERVICE, USERNAME)
    except KeyringError as exc:
        raise CredentialError(
            f"The system credential store is unavailable: {exc}. "
            f"Set {ENV_VAR} for this session instead."
        ) from exc
    return normalize_token(token) if token else None


def save_token(token: str) -> None:
    """Store a token in the OS keyring (never in a plaintext config file)."""
    try:
        keyring.set_password(SERVICE, USERNAME, normalize_token(token))
    except KeyringError as exc:
        raise CredentialError(
            f"Could not save to the system credential store: {exc}. "
            f"Set {ENV_VAR} for this session instead."
        ) from exc


def delete_token() -> None:
    """Remove the persisted token, if one exists."""
    try:
        if keyring.get_password(SERVICE, USERNAME):
            keyring.delete_password(SERVICE, USERNAME)
    except KeyringError as exc:
        raise CredentialError(f"Could not access the system credential store: {exc}") from exc
