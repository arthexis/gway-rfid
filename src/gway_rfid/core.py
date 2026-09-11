from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Tag:
    uid: bytes
    reader: str = "unknown"
    seen_at: datetime | None = None

    @property
    def uid_hex(self) -> str:
        return self.uid.hex().upper()

    def as_dict(self) -> dict[str, str]:
        seen_at = self.seen_at or datetime.now(timezone.utc)
        return {
            "uid": self.uid_hex,
            "reader": self.reader,
            "seen_at": seen_at.isoformat(),
        }


class Reader(Protocol):
    """Minimal backend contract for physical or simulated RFID readers."""

    name: str

    def scan(self) -> Tag | None:
        """Return the next observed tag, or None when no tag is present."""

    def status(self) -> dict[str, object]:
        """Return backend/device diagnostic information."""


def normalize_uid(value: bytes | bytearray | str | int) -> bytes:
    """Normalize common UID representations into immutable bytes."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, int):
        if value < 0:
            raise ValueError("RFID UID cannot be negative")
        width = max(1, (value.bit_length() + 7) // 8)
        return value.to_bytes(width, "big")
    if isinstance(value, str):
        compact = value.replace(":", "").replace("-", "").replace(" ", "")
        if compact.lower().startswith("0x"):
            compact = compact[2:]
        if len(compact) % 2:
            compact = "0" + compact
        try:
            return bytes.fromhex(compact)
        except ValueError as exc:
            raise ValueError(f"invalid RFID UID: {value!r}") from exc
    raise TypeError(f"unsupported RFID UID type: {type(value).__name__}")
