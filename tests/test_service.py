from __future__ import annotations

import signal

import pytest

from gway_rfid import service


def test_invalid_poll_interval() -> None:
    with pytest.raises(ValueError, match="interval"):
        service.run(interval=0)


def test_service_closes_reader_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class Reader:
        closed = False

        def open(self) -> None:
            pass

        def scan(self) -> None:
            raise RuntimeError("reader lost")

        def close(self) -> None:
            self.closed = True

    reader = Reader()
    monkeypatch.setattr(signal, "signal", lambda *_: None)
    with pytest.raises(RuntimeError, match="reader lost"):
        service.run(reader=reader)
    assert reader.closed
