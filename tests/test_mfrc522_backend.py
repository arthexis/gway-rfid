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
    reader = MFRC522Reader()
    tag = reader.scan()
    assert tag is not None and tag.uid_hex == "04A1B2C3"
    reader.close()
    hardware.MFRC522_StopCrypto1.assert_called()
