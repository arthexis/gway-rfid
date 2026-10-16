"""Pure presence tracking, independent of hardware, LCD and command dispatch."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gway_rfid.core import Tag


@dataclass(frozen=True)
class PresenceEvent:
    kind: str
    uid: str
    at: float
    generation: int


class PresenceTracker:
    """One scan per continuous presence, with removal hysteresis.

    A different UID starts a new presence immediately. Transient failed polls
    do not release a held card. Timestamps are monotonic seconds.
    """

    def __init__(self, removal_seconds: float = 1.2) -> None:
        if removal_seconds <= 0:
            raise ValueError("removal_seconds must be positive")
        self.removal_seconds = removal_seconds
        self.uid: str | None = None
        self.last_seen: float | None = None
        self.generation = 0

    def observe(self, tag: Tag | None, at: float) -> list[PresenceEvent]:
        events: list[PresenceEvent] = []
        incoming = tag.uid_hex if tag is not None else None
        if self.last_seen is not None and at < self.last_seen:
            raise ValueError("clock moved backwards")
        if self.uid is not None and incoming != self.uid:
            if incoming is not None or (
                self.last_seen is not None
                and at - self.last_seen >= self.removal_seconds
            ):
                events.append(PresenceEvent("removed", self.uid, at, self.generation))
                self.uid = None
                self.last_seen = None
        if incoming is not None:
            if self.uid is None:
                self.generation += 1
                self.uid = incoming
                events.append(PresenceEvent("scanned", incoming, at, self.generation))
            self.last_seen = at
        return events


def poll(reader: object, tracker: PresenceTracker, *, clock: Callable[[], float]) -> list[PresenceEvent]:
    """One iteration; caller owns reader lifecycle and scheduling."""
    return tracker.observe(reader.scan(), clock())
