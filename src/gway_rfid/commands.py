from __future__ import annotations

from gway_rfid.backends.mock import MockReader
from gway_rfid.core import normalize_uid
from gway_rfid.events import DEFAULT_QUEUE, publish_scanned


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


def scan(
    backend: str = "mock",
    uid: str | None = None,
    broker_url: str | None = None,
    queue: str = DEFAULT_QUEUE,
) -> dict[str, str] | None:
    """Perform one scan, publish `rfid.scanned`, and return the tag record."""
    tag = _reader(backend=backend, uid=uid).scan()
    if tag is None:
        return None
    record = tag.as_dict()
    publish_scanned(record, broker_url=broker_url, queue=queue)
    return record


def normalize(uid: str) -> str:
    """Normalize a UID to uppercase compact hexadecimal form."""
    return normalize_uid(uid).hex().upper()


def doctor(backend: str = "mock") -> dict[str, object]:
    """Basic diagnostic entry point; hardware checks are added per backend."""
    result = status(backend=backend)
    result["ok"] = bool(result.get("ready"))
    return result
