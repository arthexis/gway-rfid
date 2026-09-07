from __future__ import annotations

from collections.abc import Iterable

from gway_rfid.core import Tag, normalize_uid


class MockReader:
    """Deterministic reader for CI, development, and composed Gway tests."""

    name = "mock"

    def __init__(self, tags: Iterable[bytes | bytearray | str | int] = ()) -> None:
        self._tags = [Tag(normalize_uid(uid), reader=self.name) for uid in tags]

    def scan(self) -> Tag | None:
        if not self._tags:
            return None
        return self._tags.pop(0)

    def status(self) -> dict[str, object]:
        return {
            "reader": self.name,
            "ready": True,
            "queued_tags": len(self._tags),
        }
