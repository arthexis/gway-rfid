from __future__ import annotations

import sys
import types
from unittest.mock import Mock

from gway_rfid.backends.mfrc522 import MFRC522Reader


def test_import_is_hardware_independent():
    reader = MFRC522Reader()
    assert reader.status()["ready"] is False


def test_scan_and_cleanup(monkeypatch):
    gpio = types.ModuleType("RPi.GPIO")
    gpio.setwarnings = Mock()
    package = types.ModuleType("RPi")
    package.GPIO = gpio
    hardware = Mock()
    hardware.MI_OK = 0
    hardware.PICC_REQIDL = 1
    hardware.MFRC522_Request.return_value = (0, 0)
    hardware.MFRC522_Anticoll.return_value = (0, [4, 161, 178, 195])
    module = types.ModuleType("mfrc522")
    module.MFRC522 = Mock(return_value=hardware)
    monkeypatch.setitem(sys.modules, "RPi", package)
    monkeypatch.setitem(sys.modules, "RPi.GPIO", gpio)
    monkeypatch.setitem(sys.modules, "mfrc522", module)
    monkeypatch.setattr(MFRC522Reader, "_assert_device_available", lambda self: None)
    monkeypatch.setattr(MFRC522Reader, "_acquire_lock", lambda self: None)
    reader = MFRC522Reader()
    tag = reader.scan()
    assert tag is not None and tag.uid_hex == "04A1B2C3"
    reader.close()
    hardware.MFRC522_StopCrypto1.assert_called()


def test_read_block_validates_before_open():
    import pytest

    reader = MFRC522Reader()
    with pytest.raises(ValueError):
        reader.read_block(64, b"1234", key_type="A", key=b"123456")
    with pytest.raises(ValueError):
        reader.read_block(1, b"1234", key_type="X", key=b"123456")
    assert reader.status()["ready"] is False


def test_spi_owner_detection(monkeypatch, tmp_path):
    import pytest
    import os
    from pathlib import Path

    device = tmp_path / "spidev0.0"
    device.write_bytes(b"device")
    fd_dir = tmp_path / "proc" / "999999" / "fd"
    fd_dir.mkdir(parents=True)
    (fd_dir / "3").symlink_to(device)
    original_path = Path

    # Verify the fail-closed rule with a synthetic /proc tree.
    import gway_rfid.backends.mfrc522 as backend
    def fake_path(value):
        if value == "/proc":
            return tmp_path / "proc"
        if value == "/dev/spidev0.0":
            return device
        return original_path(value)
    monkeypatch.setattr(backend, "Path", fake_path)
    with pytest.raises(RuntimeError, match="already in use"):
        MFRC522Reader()._assert_device_available()


def test_open_failure_releases_lock(monkeypatch):
    import pytest
    reader = MFRC522Reader()
    monkeypatch.setattr(reader, "_acquire_lock", lambda: setattr(reader, "_lock_fd", 12345))
    monkeypatch.setattr(reader, "_assert_device_available", lambda: (_ for _ in ()).throw(RuntimeError("busy")))
    closed = []
    monkeypatch.setattr("gway_rfid.backends.mfrc522.os.close", lambda fd: closed.append(fd))
    with pytest.raises(RuntimeError, match="busy"):
        reader.open()
    assert closed == [12345]
    assert reader._lock_fd is None


def test_lock_contention(monkeypatch, tmp_path):
    import pytest
    import gway_rfid.backends.mfrc522 as backend
    from pathlib import Path
    real_path = Path
    monkeypatch.setattr(backend, "Path", lambda value: tmp_path / "lock" if str(value).startswith("/run/lock/") else real_path(value))
    first, second = MFRC522Reader(), MFRC522Reader()
    try:
        first._acquire_lock()
        with pytest.raises(RuntimeError, match="lock is held"):
            second._acquire_lock()
    finally:
        first.close()
        second.close()
