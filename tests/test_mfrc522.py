from __future__ import annotations

import sys
from types import ModuleType

import pytest

from gway_rfid.backends.mfrc522 import MFRC522Reader


class FakeChip:
    MI_OK = 0
    PICC_REQIDL = 0x26
    PICC_AUTHENT1A = 0x60
    PICC_AUTHENT1B = 0x61

    def __init__(self, **kwargs):
        self.config = kwargs
        self.request = (0, 0)
        self.anticoll = (0, [1, 2, 3, 4])
        self.auth_status = 0
        self.read_result = (0, list(range(16)))
        self.selected = []
        self.auth_calls = []
        self.read_calls = []
        self.stops = 0

    def MFRC522_Request(self, mode):
        assert mode == self.PICC_REQIDL
        return self.request

    def MFRC522_Anticoll(self):
        return self.anticoll

    def MFRC522_SelectTag(self, uid):
        self.selected.append(uid)

    def MFRC522_Auth(self, mode, block, key, uid):
        self.auth_calls.append((mode, block, key, uid))
        return self.auth_status

    def MFRC522_Read(self, block):
        self.read_calls.append(block)
        return self.read_result

    def MFRC522_StopCrypto1(self):
        self.stops += 1


@pytest.fixture
def hardware(monkeypatch):
    gpio = ModuleType("RPi.GPIO")
    gpio.warnings = []
    gpio.cleanups = 0
    gpio.setwarnings = lambda value: gpio.warnings.append(value)
    gpio.cleanup = lambda: setattr(gpio, "cleanups", gpio.cleanups + 1)
    rpi = ModuleType("RPi")
    rpi.GPIO = gpio
    module = ModuleType("mfrc522")
    chips = []

    def factory(**kwargs):
        chip = FakeChip(**kwargs)
        chips.append(chip)
        return chip

    module.MFRC522 = factory
    monkeypatch.setitem(sys.modules, "RPi", rpi)
    monkeypatch.setitem(sys.modules, "RPi.GPIO", gpio)
    monkeypatch.setitem(sys.modules, "mfrc522", module)
    return gpio, chips


def test_lazy_open_defaults_and_idempotence(hardware):
    gpio, chips = hardware
    reader = MFRC522Reader()
    assert chips == []
    reader.open()
    reader.open()
    assert len(chips) == 1
    assert chips[0].config == {"bus": 0, "device": 0, "pin_mode": 11, "pin_rst": 25}
    assert gpio.warnings == [False]
    reader.close()
    assert chips[0].stops == 1
    assert gpio.cleanups == 1
    reader.close()
    assert gpio.cleanups == 1


def test_custom_pins_and_reopen(hardware):
    gpio, chips = hardware
    reader = MFRC522Reader(bus=1, device=1, pin_mode=10, pin_rst=24)
    reader.open()
    assert chips[0].config == {"bus": 1, "device": 1, "pin_mode": 10, "pin_rst": 24}
    reader.close()
    reader.open()
    assert len(chips) == 2
    reader.close()
    assert gpio.cleanups == 2


@pytest.mark.parametrize("failure", ["request", "anticoll", "empty_uid"])
def test_detect_uid_rejects_failed_detection(hardware, failure):
    _, chips = hardware
    reader = MFRC522Reader()
    reader.open()
    chip = chips[0]
    if failure == "request":
        chip.request = (1, 0)
    elif failure == "anticoll":
        chip.anticoll = (1, [])
    else:
        chip.anticoll = (0, [])
    assert reader.detect_uid() is None
    assert chip.selected == []


def test_detect_uid_selects_card(hardware):
    _, chips = hardware
    reader = MFRC522Reader()
    assert reader.detect_uid() == bytes([1, 2, 3, 4])
    assert chips[0].selected == [[1, 2, 3, 4]]


@pytest.mark.parametrize("key_type,mode", [("A", 0x60), ("B", 0x61)])
def test_authenticated_block_read_and_crypto_cleanup(hardware, key_type, mode):
    _, chips = hardware
    reader = MFRC522Reader()
    data = reader.read_block(4, b"\x01\x02\x03\x04", key_type=key_type)
    assert data == bytes(range(16))
    chip = chips[0]
    assert chip.auth_calls == [(mode, 4, [255] * 6, [1, 2, 3, 4])]
    assert chip.read_calls == [4]
    assert chip.stops == 1


@pytest.mark.parametrize("result", [(1, [0] * 16), (0, None), (0, [0] * 15)])
def test_bad_block_result_returns_none_and_cleans_up(hardware, result):
    _, chips = hardware
    reader = MFRC522Reader()
    reader.open()
    chips[0].read_result = result
    assert reader.read_block(1, b"\x01") is None
    assert chips[0].stops == 1


def test_auth_failure_does_not_read_block(hardware):
    _, chips = hardware
    reader = MFRC522Reader()
    reader.open()
    chips[0].auth_status = 1
    assert reader.read_block(2, b"\x01") is None
    assert chips[0].read_calls == []
    assert chips[0].stops == 1


@pytest.mark.parametrize("kwargs", [
    {"block": -1, "uid": b"\x01"},
    {"block": 1, "uid": b"\x01", "key_type": "C"},
    {"block": 1, "uid": b"\x01", "key": b"short"},
])
def test_invalid_read_arguments_do_not_open_hardware(hardware, kwargs):
    _, chips = hardware
    with pytest.raises(ValueError):
        MFRC522Reader().read_block(**kwargs)
    assert chips == []


def test_raw_read_response_supported(hardware):
    _, chips = hardware
    reader = MFRC522Reader()
    reader.open()
    chips[0].read_result = list(range(16))
    assert reader.read_block(3, b"\x01") == bytes(range(16))
    assert chips[0].stops == 1
