from gway_rfid import commands


def test_status_uses_mock_backend_by_default():
    status = commands.status()
    assert status["reader"] == "mock"
    assert status["ready"] is True


def test_scan_normalizes_mock_uid():
    tag = commands.scan(uid="04:a1:b2:c3")
    assert tag is not None
    assert tag["uid"] == "04A1B2C3"
    assert tag["reader"] == "mock"


def test_doctor_reports_ok():
    assert commands.doctor()["ok"] is True
