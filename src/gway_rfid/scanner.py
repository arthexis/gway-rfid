"""Synchronous, single-owner RFID polling lifecycle.

Recovery, persistence and signal handling are deliberately outside this module.
"""
from __future__ import annotations

from collections.abc import Callable
from threading import Event
from time import monotonic
from typing import Protocol

from gway_rfid.core import Reader
from gway_rfid.presence import PresenceEvent, PresenceTracker


class ClosableReader(Reader, Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...


class Scanner:
    """Poll one reader until asked to stop; emit presence transitions once."""

    def __init__(
        self,
        reader: ClosableReader,
        *,
        on_event: Callable[[PresenceEvent], None],
        poll_interval: float = 0.1,
        removal_seconds: float = 1.2,
        clock: Callable[[], float] = monotonic,
        stop_event: Event | None = None,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        self.reader = reader
        self.on_event = on_event
        self.poll_interval = poll_interval
        self.tracker = PresenceTracker(removal_seconds)
        self.clock = clock
        self._stop = stop_event if stop_event is not None else Event()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def stop(self) -> None:
        """Request shutdown; interrupt the wait between polls."""
        self._stop.set()

    def run(self) -> None:
        if self._running:
            raise RuntimeError("scanner already running")
        if self._stop.is_set():
            return
        self._running = True
        try:
            self.reader.open()
            while not self._stop.is_set():
                tag = self.reader.scan()
                for event in self.tracker.observe(tag, self.clock()):
                    self.on_event(event)
                self._stop.wait(self.poll_interval)
        finally:
            try:
                self.reader.close()
            finally:
                self._running = False
