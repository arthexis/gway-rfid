from __future__ import annotations

from gway_rfid.backends.mock import MockReader
from gway_rfid.core import normalize_uid


def _reader(*, backend: str = "mock", uid: str | None = None) -> MockReader:
    if backend != "mock":
        raise ValueError(
            f"unsupported backend {backend!r}; hardware backends will be migrated next"
        )
    tags = [uid] if uid else []
    return MockReader(tags)


def status(backend: str = "mock") -> dict[str, object]:
    """Return reader/backend status without requiring physical hardware."""
    return _reader(backend=backend).status()


def scan(backend: str = "mock", uid: str | None = None) -> dict[str, str] | None:
    """Perform one scan and return a normalized tag record."""
    tag = _reader(backend=backend, uid=uid).scan()
    return tag.as_dict() if tag else None


def normalize(uid: str) -> str:
    """Normalize a UID to uppercase compact hexadecimal form."""
    return normalize_uid(uid).hex().upper()


def doctor(backend: str = "mock") -> dict[str, object]:
    """Basic diagnostic entry point; hardware checks are added per backend."""
    result = status(backend=backend)
    result["ok"] = bool(result.get("ready"))
    return result
