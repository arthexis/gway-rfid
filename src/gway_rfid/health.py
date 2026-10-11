"""In-memory scanner health; no I/O or service dependency."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ScannerHealth:
    state: str = "stopped"
    polls: int = 0
    scans: int = 0
    errors: int = 0
    recoveries: int = 0
    last_poll: str | None = None
    last_scan: str | None = None
    last_error: str | None = None
    started_at: str | None = None
    started_monotonic: float | None = None
    last_poll_monotonic: float | None = None
    present_uid: str | None = None

    def snapshot(self, *, now: float, freshness_seconds: float = 2.0) -> dict[str, object]:
        if freshness_seconds <= 0:
            raise ValueError("freshness_seconds must be positive")
        age = None if self.last_poll_monotonic is None else max(0.0, now - self.last_poll_monotonic)
        result = asdict(self)
        result.pop("started_monotonic")
        result.pop("last_poll_monotonic")
        result["uptime_seconds"] = (
            None if self.started_monotonic is None else max(0.0, now - self.started_monotonic)
        )
        result["poll_age_seconds"] = age
        result["healthy"] = self.state == "running" and age is not None and age <= freshness_seconds
        return result
