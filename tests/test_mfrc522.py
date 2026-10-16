"""Hardware-independent contract tests for the existing MFRC522 backend."""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import Mock

import pytest

from gway_rfid.backends.mfrc522 import MFRC522Reader


class Chip:
    MI_OK = 0
    PICC_REQIDL = 0x26
    PICC_AUTHENT1A = 0x60
    PICC_AUTHENT1B = 0x61

    def __init__(self, **config):
        self.config = config
        self.request = (0, None)
        self.anticoll = (0, [1, 2, 3, 4])
        self.auth_status = 0
        self.read_result = (0, list(range(16)))
        self.spi = Mock()
        self.MFRC522_SelectTag = Mock()
        self.MFRC522_Auth = Mock(side_effect=lambda *args: self.auth_status)
        self.MFRC522_Read = Mock(side_effect=lambda block: self.read_result)
        self.MFRC522_StopCrypto1 = Mock()

    def MFRC522_Request(self, mode):
        assert mode == self.PICC_REQIDL
        return self.request

    def MFRC522_Anticoll(self):
        return self.anticoll


@pytest.fixture
def hardware(monkeypatch):
    gpio = ModuleType("RPi.GPIO")
    gpio.setwarnings = Mock()
    rpi = ModuleType("RPi")
    rpi.GPIO = gpio
    module = ModuleType("mfrc522")
    chips = []

    def factory(**kwargs):
        chip = Chip(**kwargs)
        chips.append(chip)
        return chip

    module.MFRC522 = factory
    monkeypatch.setitem(sys.modules, "RPi", rpi)
    monkeypatch.setitem(sys.modules, "RPi.GPIO", gpio)
    monkeypatch.setitem(sys.modules, "mfrc522", module)
    monkeypatch.setattr(MFRC522Reader, "_acquire_lock", lambda self: None)
    monkeypatch.setattr(MFRC522Reader, "_assert_device_available", lambda self: None)
    return gpio, chips


def test_open_is_lazy_idempotent_and_close_releases_spi(hardware):
    gpio, chips = hardware
    reader = MFRC522Reader()
    assert chips == []
    reader.open()
    reader.open()
    assert len(chips) == 1
    assert chips[0].config == {"bus": 0, "device": 0, "pin_mode": 11, "pin_rst": 25}
    gpio.setwarnings.assert_called_once_with(False)
    assert reader.status()["ready"] is True
    reader.close()
    chips[0].spi.close.assert_called_once()
    assert reader.status()["ready"] is False
    reader.close()
    chips[0].spi.close.assert_called_once()


def test_custom_hardware_parameters(hardware):
    _, chips = hardware
    reader = MFRC522Reader(1, 1, 10, 24)
    reader.open()
    assert chips[0].config == {"bus": 1, "device": 1, "pin_mode": 10, "pin_rst": 24}
    reader.close()


@pytest.mark.parametrize("failure", ["request", "anticoll", "empty"])
def test_scan_returns_none_for_absent_or_invalid_card(hardware, failure):
    _, chips = hardware
    reader = MFRC522Reader()
    reader.open()
    if failure == "request":
        chips[0].request = (1, None)
    elif failure == "anticoll":
        chips[0].anticoll = (1, [])
    else:
        chips[0].anticoll = (0, [])
    assert reader.scan() is None
    chips[0].MFRC522_SelectTag.assert_not_called()
    reader.close()


def test_scan_returns_tag_and_selects_uid(hardware):
    _, chips = hardware
    reader = MFRC522Reader()
    tag = reader.scan()
    assert tag is not None
    assert tag.uid == b"\x01\x02\x03\x04"
    assert tag.reader == "mfrc522"
    chips[0].MFRC522_SelectTag.assert_called_once_with([1, 2, 3, 4])
    reader.close()


@pytest.mark.parametrize("kind,mode", [("A", 0x60), ("B", 0x61)])
def test_authenticated_block_read(hardware, kind, mode):
    _, chips = hardware
    reader = MFRC522Reader()
    assert reader.read_block(4, b"\x01\x02", key_type=kind, key=b"\xff" * 6) == bytes(range(16))
    chips[0].MFRC522_Auth.assert_called_once_with(mode, 4, [255] * 6, [1, 2])
    chips[0].MFRC522_Read.assert_called_once_with(4)
    chips[0].MFRC522_StopCrypto1.assert_called_once()
    reader.close()


def test_auth_failure_does_not_read_and_stops_crypto(hardware):
    _, chips = hardware
    reader = MFRC522Reader()
    reader.open()
    chips[0].auth_status = 1
    assert reader.read_block(1, b"\x01", key_type="A", key=b"\xff" * 6) is None
    chips[0].MFRC522_Read.assert_not_called()
    chips[0].MFRC522_StopCrypto1.assert_called_once()
    reader.close()


@pytest.mark.parametrize("result", [(1, [0] * 16), (0, None), (0, [0] * 15)])
def test_invalid_block_response_stops_crypto(hardware, result):
    _, chips = hardware
    reader = MFRC522Reader()
    reader.open()
    chips[0].read_result = result
    assert reader.read_block(2, b"\x01", key_type="B", key=b"\xff" * 6) is None
    chips[0].MFRC522_StopCrypto1.assert_called_once()
    reader.close()


@pytest.mark.parametrize("block,kind,key", [
    (-1, "A", b"\xff" * 6), (64, "A", b"\xff" * 6),
    (1, "C", b"\xff" * 6), (1, "A", b"short"),
])
def test_invalid_read_does_not_open_device(hardware, block, kind, key):
    _, chips = hardware
    with pytest.raises(ValueError):
        MFRC522Reader().read_block(block, b"\x01", key_type=kind, key=key)
    assert chips == []


def test_raw_block_response_supported(hardware):
    _, chips = hardware
    reader = MFRC522Reader()
    reader.open()
    chips[0].read_result = list(range(16))
    assert reader.read_block(1, b"\x01", key_type="A", key=b"\xff" * 6) == bytes(range(16))
    reader.close()


def test_open_failure_preserves_closed_state(hardware, monkeypatch):
    _, chips = hardware
    reader = MFRC522Reader()
    def fail():
        raise RuntimeError("device busy")
    monkeypatch.setattr(reader, "_assert_device_available", fail)
    with pytest.raises(RuntimeError, match="device busy"):
        reader.open()
    assert chips == []
    assert reader.status()["ready"] is False


def test_lock_acquisition_and_release(monkeypatch, tmp_path):
    import os
    import fcntl
    from pathlib import Path

    reader = MFRC522Reader()
    lock_path = tmp_path / "reader.lock"
    real_path = Path

    # Replace only the backend's lock-path constructor.
    import gway_rfid.backends.mfrc522 as backend
    monkeypatch.setattr(backend, "Path", lambda _value: lock_path)
    reader._acquire_lock()
    assert reader._lock_fd is not None
    original_fd = reader._lock_fd
    reader._acquire_lock()
    assert reader._lock_fd == original_fd
    competitor = MFRC522Reader()
    with pytest.raises(RuntimeError, match="lock is held"):
        competitor._acquire_lock()
    reader.close()
    assert reader._lock_fd is None
    competitor._acquire_lock()
    competitor.close()


def test_device_missing_fails_closed(monkeypatch, tmp_path):
    import gway_rfid.backends.mfrc522 as backend

    missing = tmp_path / "missing-spi"
    monkeypatch.setattr(backend, "Path", lambda _value: missing)
    with pytest.raises(RuntimeError, match="SPI device unavailable"):
        MFRC522Reader()._assert_device_available()


def test_device_owner_detected(monkeypatch, tmp_path):
    import os
    import gway_rfid.backends.mfrc522 as backend

    device = tmp_path / "spidev0.0"
    device.write_bytes(b"device")
    proc = tmp_path / "proc"
    fd_dir = proc / "987654" / "fd"
    fd_dir.mkdir(parents=True)
    (fd_dir / "3").symlink_to(device)
    real_path = backend.Path

    def fake_path(value):
        if value == "/proc":
            return proc
        if str(value).startswith("/dev/spidev"):
            return device
        return real_path(value)

    monkeypatch.setattr(backend, "Path", fake_path)
    with pytest.raises(RuntimeError, match="already in use"):
        MFRC522Reader()._assert_device_available()


def test_open_failure_releases_real_lock(monkeypatch, tmp_path):
    import gway_rfid.backends.mfrc522 as backend

    lock_path = tmp_path / "reader.lock"
    monkeypatch.setattr(backend, "Path", lambda _value: lock_path)
    reader = MFRC522Reader()
    monkeypatch.setattr(reader, "_assert_device_available",
                        lambda: (_ for _ in ()).throw(RuntimeError("missing SPI")))
    with pytest.raises(RuntimeError, match="missing SPI"):
        reader.open()
    assert reader._lock_fd is None
    other = MFRC522Reader()
    other._acquire_lock()
    other.close()


def test_context_manager_closes_on_exception(hardware):
    _, chips = hardware
    reader = MFRC522Reader()
    with pytest.raises(RuntimeError, match="failure"):
        with reader:
            raise RuntimeError("failure")
    assert reader.status()["ready"] is False
    chips[0].spi.close.assert_called_once()


def test_read_exception_still_stops_crypto(hardware):
    _, chips = hardware
    reader = MFRC522Reader()
    reader.open()
    chips[0].MFRC522_Read.side_effect = OSError("SPI read failed")
    with pytest.raises(OSError, match="SPI read failed"):
        reader.read_block(1, b"\x01", key_type="A", key=b"\xff" * 6)
    chips[0].MFRC522_StopCrypto1.assert_called_once()
    reader.close()
