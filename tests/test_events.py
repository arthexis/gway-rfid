import sys
from types import SimpleNamespace

from gway_rfid import events


class FakeQueue:
    def __init__(self):
        self.messages = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def put(self, payload, *, serializer):
        self.messages.append((payload, serializer))


class FakeConnection:
    last = None

    def __init__(self, url, connect_timeout):
        self.url = url
        self.connect_timeout = connect_timeout
        self.queue = FakeQueue()
        self.queue_name = None
        FakeConnection.last = self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def SimpleQueue(self, name):
        self.queue_name = name
        return self.queue


def test_publish_scanned_uses_plain_json_event(monkeypatch):
    monkeypatch.setitem(sys.modules, "kombu", SimpleNamespace(Connection=FakeConnection))
    assert events.publish_scanned(
        {"uid": "04A1B2C3", "reader": "mock", "seen_at": "2026-09-15T00:00:00+00:00"},
        broker_url="redis://localhost:6379/0",
    ) is True
    connection = FakeConnection.last
    assert connection.queue_name == "ocpp.authorization"
    payload, serializer = connection.queue.messages[0]
    assert serializer == "json"
    assert payload == {
        "type": "rfid.scanned",
        "uid": "04A1B2C3",
        "reader": "mock",
        "seen_at": "2026-09-15T00:00:00+00:00",
    }


def test_missing_broker_is_nonfatal(monkeypatch):
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    assert events.publish_scanned({"uid": "04A1B2C3"}) is False


def test_broker_failure_is_nonfatal(monkeypatch):
    class BrokenConnection:
        def __init__(self, *_args, **_kwargs):
            raise OSError("offline")

    monkeypatch.setitem(sys.modules, "kombu", SimpleNamespace(Connection=BrokenConnection))
    assert events.publish_scanned(
        {"uid": "04A1B2C3"}, broker_url="redis://localhost:6379/0"
    ) is False
