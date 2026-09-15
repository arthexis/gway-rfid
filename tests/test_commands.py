from gway_rfid import commands


def test_status_uses_mock_backend_by_default():
    status = commands.status()
    assert status["reader"] == "mock"
    assert status["ready"] is True


def test_scan_normalizes_mock_uid(monkeypatch):
    published = []

    def publish(record, *, broker_url=None, queue=None):
        published.append((record, broker_url, queue))
        return True

    monkeypatch.setattr(commands, "publish_scanned", publish)
    tag = commands.scan(uid="04:a1:b2:c3")
    assert tag is not None
    assert tag["uid"] == "04A1B2C3"
    assert tag["reader"] == "mock"
    assert published == [(tag, None, "ocpp.authorization")]


def test_scan_can_target_explicit_broker_and_queue(monkeypatch):
    published = []

    def publish(record, *, broker_url=None, queue=None):
        published.append((record, broker_url, queue))
        return True

    monkeypatch.setattr(commands, "publish_scanned", publish)
    tag = commands.scan(
        uid="04A1B2C3",
        broker_url="redis://localhost:6379/0",
        queue="local.events",
    )
    assert published == [(tag, "redis://localhost:6379/0", "local.events")]


def test_scan_still_returns_record_when_publication_fails(monkeypatch):
    monkeypatch.setattr(commands, "publish_scanned", lambda *args, **kwargs: False)
    tag = commands.scan(uid="04A1B2C3")
    assert tag is not None
    assert tag["uid"] == "04A1B2C3"


def test_doctor_reports_ok():
    assert commands.doctor()["ok"] is True
