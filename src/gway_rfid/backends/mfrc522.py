"""MFRC522 block transport extracted from AP Kiosk's historical scanner.

Raspberry Pi dependencies are imported only when hardware is opened.
"""
from __future__ import annotations

from typing import Any


class MFRC522Reader:
    """Poll UIDs and read authenticated MIFARE Classic blocks."""

    def __init__(
        self, *, bus: int = 0, device: int = 0,
        pin_mode: int = 11, pin_rst: int = 25,
    ) -> None:
        self.bus = bus
        self.device = device
        self.pin_mode = pin_mode  # GPIO.BCM
        self.pin_rst = pin_rst
        self._mfrc: Any | None = None

    def open(self) -> None:
        if self._mfrc is not None:
            return
        import RPi.GPIO as GPIO  # type: ignore[import-not-found]
        from mfrc522 import MFRC522  # type: ignore[import-not-found]

        GPIO.setwarnings(False)
        self._mfrc = MFRC522(
            bus=self.bus, device=self.device,
            pin_mode=self.pin_mode, pin_rst=self.pin_rst,
        )

    @property
    def mfrc(self) -> Any:
        if self._mfrc is None:
            self.open()
        return self._mfrc

    def detect_uid(self) -> bytes | None:
        mfrc = self.mfrc
        status, _ = mfrc.MFRC522_Request(mfrc.PICC_REQIDL)
        if status != mfrc.MI_OK:
            return None
        status, uid = mfrc.MFRC522_Anticoll()
        if status != mfrc.MI_OK or not uid:
            return None
        mfrc.MFRC522_SelectTag(uid)
        return bytes(uid)

    def read_block(
        self, block: int, uid: bytes, *,
        key_type: str = "A", key: bytes = b"\xff" * 6,
    ) -> bytes | None:
        if block < 0 or len(key) != 6 or key_type not in ("A", "B"):
            raise ValueError("invalid block, key type, or six-byte key")
        mfrc = self.mfrc
        mode = mfrc.PICC_AUTHENT1B if key_type == "B" else mfrc.PICC_AUTHENT1A
        try:
            status = mfrc.MFRC522_Auth(mode, block, list(key), list(uid))
            if status != mfrc.MI_OK:
                return None
            result = mfrc.MFRC522_Read(block)
            if isinstance(result, tuple):
                read_status, data = result
            else:
                read_status, data = mfrc.MI_OK, result
            if read_status != mfrc.MI_OK or data is None or len(data) != 16:
                return None
            return bytes(data)
        finally:
            self.close_crypto()

    def close_crypto(self) -> None:
        if self._mfrc is not None:
            self._mfrc.MFRC522_StopCrypto1()

    def close(self) -> None:
        if self._mfrc is None:
            return
        try:
            self.close_crypto()
        finally:
            self._mfrc = None
            import RPi.GPIO as GPIO  # type: ignore[import-not-found]
            GPIO.cleanup()
