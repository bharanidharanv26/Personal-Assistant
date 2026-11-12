import secrets

import keyring
from keyring.errors import KeyringError

from nila.core.config import Settings

SERVICE = "NILA-AI"


def read_credential(name: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, name)
    except KeyringError as exc:
        raise RuntimeError(
            "Credential store unavailable. Configure NILA_API_TOKEN and, for hosted "
            "reasoning, NILA_OPENAI_API_KEY through the environment."
        ) from exc


def store_credential(name: str, value: str) -> None:
    try:
        keyring.set_password(SERVICE, name, value)
    except KeyringError as exc:
        raise RuntimeError("Could not save the credential to the operating system store.") from exc


def api_token(settings: Settings, *, create: bool = False) -> str:
    if settings.api_token is not None:
        return settings.api_token.get_secret_value()
    token = read_credential("api-token")
    if token is None and create:
        token = secrets.token_urlsafe(48)
        store_credential("api-token", token)
    if token is None:
        raise RuntimeError("No local API token. Run `nila auth init` or start `nila serve` first.")
    if len(token) < 32:
        raise RuntimeError("Stored API token is too short. Run `nila auth init --rotate`.")
    return token


def openai_key(settings: Settings) -> str:
    if settings.openai_api_key is not None:
        value = settings.openai_api_key.get_secret_value().strip()
    else:
        value = (read_credential("openai-api-key") or "").strip()
    if not value:
        raise RuntimeError("Set a provider key with `nila auth set-openai-key`.")
    return value
