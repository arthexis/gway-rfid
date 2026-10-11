"""Synchronous, single-owner RFID polling lifecycle.

Persistence and signal handling are deliberately outside this module.
"""
from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from threading import Event
from time import monotonic
from typing import Protocol

from gway_rfid.core import Reader
from gway_rfid.presence import PresenceEvent, PresenceTracker


class ClosableReader(Reader, Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...


class ReaderOwnershipError(RuntimeError):
    """Another process owns the reader; never retry automatically."""


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
        retry_initial: float = 1.0,
        retry_max: float = 30.0,
        recoverable: Callable[[Exception], bool] | None = None,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        if retry_initial <= 0 or retry_max < retry_initial:
            raise ValueError("invalid retry delays")
        self.retry_initial = retry_initial
        self.retry_max = retry_max
        self.recoverable = recoverable or self._recoverable
        self.recoveries = 0
        self.last_error: str | None = None
        self.state = "stopped"
        self.reader = reader
        self.on_event = on_event
        self.poll_interval = poll_interval
        self.tracker = PresenceTracker(removal_seconds)
        self.clock = clock
        self._stop = stop_event if stop_event is not None else Event()
        self._running = False

    @staticmethod
    def _recoverable(error: Exception) -> bool:
        if isinstance(error, ReaderOwnershipError):
            return False
        if isinstance(error, (ValueError, TypeError, ImportError, PermissionError)):
            return False
        if isinstance(error, RuntimeError) and any(
            marker in str(error).lower()
            for marker in ("already in use", "lock is held", "cannot inspect", "cannot verify", "unavailable")
        ):
            return False
        return isinstance(error, (OSError, RuntimeError))

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
        delay = self.retry_initial
        opened = False
        self.state = "starting"
        try:
            while not self._stop.is_set():
                try:
                    if not opened:
                        self.reader.open()
                        opened = True
                    tag = self.reader.scan()
                except Exception as error:
                    self.last_error = f"{type(error).__name__}: {error}"
                    try:
                        self.reader.close()
                    finally:
                        opened = False
                    if not self.recoverable(error):
                        self.state = "failed"
                        raise
                    self.state = "recovering"
                    self.recoveries += 1
                    self._stop.wait(delay)
                    delay = min(delay * 2, self.retry_max)
                    continue
                self.state = "running"
                self.last_error = None
                delay = self.retry_initial
                for event in self.tracker.observe(tag, self.clock()):
                    self.on_event(event)
                self._stop.wait(self.poll_interval)
        finally:
            try:
                self.reader.close()
            finally:
                self._running = False
                if self.state != "failed":
                    self.state = "stopped"
