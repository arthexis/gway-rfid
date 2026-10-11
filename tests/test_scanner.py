from __future__ import annotations

from threading import Event
from unittest.mock import Mock

import pytest

from gway_rfid.core import Tag
from gway_rfid.scanner import Scanner


class FakeReader:
    def __init__(self, observations=()):
        self.observations = iter(observations)
        self.opened = 0
        self.closed = 0

    def open(self):
        self.opened += 1

    def close(self):
        self.closed += 1

    def scan(self):
        return next(self.observations)

    def status(self):
        return {"ready": bool(self.opened and not self.closed)}


class ImmediateStop:
    def __init__(self, after=1):
        self.stopped = False
        self.after = after
        self.waits = 0

    def is_set(self):
        return self.stopped

    def set(self):
        self.stopped = True

    def wait(self, _seconds):
        self.waits += 1
        if self.waits >= self.after:
            self.set()
        return self.stopped


def test_polling_suppresses_held_cards():
    tag = Tag(b"\x01\x02")
    reader = FakeReader([tag, tag, None, None])
    events = []
    scanner = Scanner(reader, on_event=events.append, stop_event=ImmediateStop(4),
                      clock=iter([0.0, 0.1, 0.3, 1.5]).__next__)
    scanner.run()
    assert [(event.kind, event.uid) for event in events] == [
        ("scanned", "0102"), ("removed", "0102")
    ]
    assert reader.opened == reader.closed == 1
    assert not scanner.running


def test_callback_error_closes_reader():
    reader = FakeReader([Tag(b"\x01")])
    scanner = Scanner(reader, on_event=Mock(side_effect=ValueError("delivery failed")),
                      stop_event=ImmediateStop())
    with pytest.raises(ValueError, match="delivery failed"):
        scanner.run()
    assert reader.closed == 1


def test_open_error_still_closes_reader():
    reader = FakeReader()
    reader.open = Mock(side_effect=OSError("SPI failed"))
    scanner = Scanner(reader, on_event=lambda event: None)
    with pytest.raises(OSError, match="SPI failed"):
        scanner.run()
    assert reader.closed == 1


def test_pre_stopped_scanner_never_opens_reader():
    stop = Event()
    stop.set()
    reader = FakeReader()
    Scanner(reader, on_event=lambda event: None, stop_event=stop).run()
    assert reader.opened == 0


def test_invalid_poll_interval():
    with pytest.raises(ValueError):
        Scanner(FakeReader(), on_event=lambda event: None, poll_interval=0)
