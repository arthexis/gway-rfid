"""Synchronous, single-owner RFID polling lifecycle.

Persistence and signal handling are deliberately outside this module.
"""
from __future__ import annotations

from collections.abc import Callable
from threading import Event, Lock
from time import monotonic
from typing import Protocol

from gway_rfid.core import Reader
from gway_rfid.health import ScannerHealth, utc_iso
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
        self.health = ScannerHealth()
        self.state = "stopped"
        self.reader = reader
        self.on_event = on_event
        self.poll_interval = poll_interval
        self.tracker = PresenceTracker(removal_seconds)
        self.clock = clock
        self._stop = stop_event if stop_event is not None else Event()
        self._running = False
        self._run_lock = Lock()

    @property
    def state(self) -> str:
        return self.health.state

    @state.setter
    def state(self, value: str) -> None:
        self.health.state = value

    def status(self, *, freshness_seconds: float = 2.0) -> dict[str, object]:
        """Passive snapshot; never opens or polls hardware."""
        result = self.health.snapshot(now=self.clock(), freshness_seconds=freshness_seconds)
        result["backend"] = self.reader.name if hasattr(self.reader, "name") else type(self.reader).__name__
        return result

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
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("scanner already running")
        if self._stop.is_set():
            self._run_lock.release()
            return
        self._running = True
        delay = self.retry_initial
        opened = False
        needs_close = True
        self.state = "starting"
        self.health.started_at = utc_iso()
        self.health.started_monotonic = self.clock()
        try:
            while not self._stop.is_set():
                try:
                    if not opened:
                        self.reader.open()
                        opened = True
                        needs_close = True
                    tag = self.reader.scan()
                except Exception as error:
                    self.last_error = f"{type(error).__name__}: {error}"
                    self.health.last_error = self.last_error
                    self.health.errors += 1
                    try:
                        self.reader.close()
                    finally:
                        opened = False
                        needs_close = False
                    if not self.recoverable(error):
                        self.state = "failed"
                        raise
                    self.state = "recovering"
                    self.recoveries += 1
                    self.health.recoveries = self.recoveries
                    self._stop.wait(delay)
                    delay = min(delay * 2, self.retry_max)
                    continue
                self.state = "running"
                self.last_error = None
                self.health.last_error = None
                now = self.clock()
                self.health.polls += 1
                self.health.last_poll_monotonic = now
                self.health.last_poll = utc_iso()
                delay = self.retry_initial
                events = self.tracker.observe(tag, now)
                self.health.present_uid = self.tracker.uid
                for event in events:
                    if event.kind == "scanned":
                        self.health.scans += 1
                        self.health.last_scan = utc_iso()
                    self.on_event(event)
                self._stop.wait(self.poll_interval)
        finally:
            try:
                if needs_close:
                    self.reader.close()
            finally:
                self._running = False
                if self.state != "failed":
                    self.state = "stopped"
                self._run_lock.release()
