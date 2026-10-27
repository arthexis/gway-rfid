"""Mocked Linux USB printer transport tests."""
import pytest
from gway_rfid import linux_printing


class Endpoint:
    bEndpointAddress = 0x01
    bmAttributes = 0x02


class Config:
    def __getitem__(self, key):
        assert key == (0, 0)
        return [Endpoint()]


class Device:
    bus = 1
    address = 2

    def __init__(self, short=False):
        self.chunks = []
        self.short = short

    def get_active_configuration(self):
        return Config()

    def write(self, endpoint, data, *, interface):
        assert endpoint == 1 and interface == 0
        self.chunks.append(bytes(data))
        return len(data) - int(self.short)


class Core:
    def __init__(self, devices):
        self.devices = devices
        self.requests = []

    def find(self, **kwargs):
        self.requests.append(kwargs)
        return self.devices


class Util:
    ENDPOINT_OUT = 0
    ENDPOINT_TYPE_BULK = 2

    @staticmethod
    def endpoint_direction(address):
        return address & 0x80

    @staticmethod
    def endpoint_type(attributes):
        return attributes & 3


def test_linux_usb_mocked_write(monkeypatch):
    monkeypatch.setattr(linux_printing.sys, "platform", "linux")
    device = Device()
    core = Core([device])
    count = linux_printing.write_linux_usb(
        b"abcdef", endpoint=1, chunk_size=2, delay_seconds=0,
        usb_core=core, usb_util=Util(),
    )
    assert count == 6
    assert device.chunks == [b"ab", b"cd", b"ef"]
    assert core.requests[0]["idVendor"] == 0x0483
    assert core.requests[0]["idProduct"] == 0x5740


def test_linux_requires_explicit_endpoint(monkeypatch):
    monkeypatch.setattr(linux_printing.sys, "platform", "linux")
    with pytest.raises(ValueError, match="endpoint"):
        linux_printing.write_linux_usb(b"x", usb_core=Core([Device()]), usb_util=Util())


def test_linux_rejects_ambiguous_devices(monkeypatch):
    monkeypatch.setattr(linux_printing.sys, "platform", "linux")
    with pytest.raises(OSError, match="exactly one"):
        linux_printing.write_linux_usb(b"x", endpoint=1, usb_core=Core([Device(), Device()]), usb_util=Util())


def test_linux_short_write_is_failure(monkeypatch):
    monkeypatch.setattr(linux_printing.sys, "platform", "linux")
    with pytest.raises(OSError, match="Short USB write"):
        linux_printing.write_linux_usb(b"x", endpoint=1, usb_core=Core([Device(short=True)]), usb_util=Util(), delay_seconds=0)


def test_linux_requires_platform(monkeypatch):
    monkeypatch.setattr(linux_printing.sys, "platform", "win32")
    with pytest.raises(OSError, match="requires Linux"):
        linux_printing.write_linux_usb(b"x", endpoint=1, usb_core=Core([Device()]), usb_util=Util())
