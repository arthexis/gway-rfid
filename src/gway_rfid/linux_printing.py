"""Optional Linux USB bulk transport for a verified Phomemo M220 interface.

Requires PyUSB and a working libusb backend. No device is opened on import.
"""
from __future__ import annotations

import sys
import time

DEFAULT_VID = 0x0483
DEFAULT_PID = 0x5740


def find_linux_printers(*, usb_core=None, vendor_id=DEFAULT_VID, product_id=DEFAULT_PID):
    """Return matching USB devices; callers must check interface/endpoint before printing."""
    if sys.platform != "linux":
        return []
    if usb_core is None:
        try:
            import usb.core as usb_core
        except ImportError as exc:
            raise RuntimeError("Linux USB printing requires the optional pyusb package") from exc
    return list(usb_core.find(find_all=True, idVendor=vendor_id, idProduct=product_id) or [])


def write_linux_usb(
    data: bytes, *, vendor_id=DEFAULT_VID, product_id=DEFAULT_PID,
    bus=None, address=None, interface=0, endpoint=None,
    chunk_size=16, delay_seconds=0.04, usb_core=None, usb_util=None,
):
    """Send a raw job to a single explicitly identified bulk OUT endpoint.

    Does not detach kernel drivers or silently select among multiple devices.
    An explicit endpoint is required, so autodetection cannot accidentally write
    to an unrelated STM32 device sharing the legacy VID/PID.
    """
    if sys.platform != "linux":
        raise OSError("Linux USB transport requires Linux")
    if not isinstance(data, bytes):
        raise TypeError("Print data must be bytes")
    if chunk_size <= 0 or delay_seconds < 0:
        raise ValueError("Invalid USB chunk size or delay")
    if endpoint is None or not (1 <= endpoint <= 255) or endpoint & 0x80:
        raise ValueError("Provide the verified USB bulk OUT --endpoint (e.g. 0x01)")
    if usb_core is None:
        try:
            import usb.core as usb_core
        except ImportError as exc:
            raise RuntimeError("Install gway-rfid[linux-printing] for PyUSB support") from exc
    if usb_util is None:
        try:
            import usb.util as usb_util
        except ImportError as exc:
            raise RuntimeError("Install gway-rfid[linux-printing] for PyUSB support") from exc
    candidates = [
        device for device in find_linux_printers(
            usb_core=usb_core, vendor_id=vendor_id, product_id=product_id
        )
        if (bus is None or device.bus == bus)
        and (address is None or device.address == address)
    ]
    if len(candidates) != 1:
        raise OSError(f"Expected exactly one matching USB printer, found {len(candidates)}")
    device = candidates[0]
    configuration = device.get_active_configuration()
    selected_interface = configuration[(interface, 0)]
    matched = [
        item for item in selected_interface
        if item.bEndpointAddress == endpoint
        and usb_util.endpoint_direction(item.bEndpointAddress) == usb_util.ENDPOINT_OUT
        and usb_util.endpoint_type(item.bmAttributes) == usb_util.ENDPOINT_TYPE_BULK
    ]
    if len(matched) != 1:
        raise ValueError("Selected endpoint is not a bulk OUT endpoint on the chosen interface")
    total = 0
    for offset in range(0, len(data), chunk_size):
        chunk = data[offset:offset + chunk_size]
        written = int(device.write(endpoint, chunk, interface=interface))
        if written != len(chunk):
            raise OSError(f"Short USB write at byte {offset}: {written}/{len(chunk)}")
        total += written
        if delay_seconds:
            time.sleep(delay_seconds)
    return total
