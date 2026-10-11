"""MFRC522 SPI backend extracted from gway-ap-kiosk field revision 1c602d5.

Hardware libraries are imported only when the reader is opened. Only the
reader owner may instantiate/open this backend on a live device.
"""
from __future__ import annotations

from typing import Any

from gway_rfid.core import Tag


class MFRC522Reader:
    name = "mfrc522"

    def __init__(self, bus: int = 0, device: int = 0, pin_mode: int = 11, pin_rst: int = 25) -> None:
        self.bus, self.device = bus, device
        self.pin_mode, self.pin_rst = pin_mode, pin_rst
        self._reader: Any | None = None

    def open(self) -> None:
        if self._reader is not None:
            return
        import RPi.GPIO as GPIO  # type: ignore[import-not-found]
        from mfrc522 import MFRC522  # type: ignore[import-not-found]

        GPIO.setwarnings(False)
        self._reader = MFRC522(
            bus=self.bus, device=self.device,
            pin_mode=self.pin_mode, pin_rst=self.pin_rst,
        )

    def scan(self) -> Tag | None:
        self.open()
        reader = self._reader
        status, _ = reader.MFRC522_Request(reader.PICC_REQIDL)
        if status != reader.MI_OK:
            return None
        status, uid = reader.MFRC522_Anticoll()
        if status != reader.MI_OK or not uid:
            return None
        reader.MFRC522_SelectTag(uid)
        return Tag(uid=bytes(uid), reader=self.name)

    def read_block(self, block: int, uid: bytes, *, key_type: str, key: bytes) -> bytes | None:
        self.open()
        reader = self._reader
        if key_type not in ("A", "B") or len(key) != 6:
            raise ValueError("key_type must be A/B and key must be six bytes")
        mode = reader.PICC_AUTHENT1B if key_type == "B" else reader.PICC_AUTHENT1A
        try:
            if reader.MFRC522_Auth(mode, block, list(key), list(uid)) != reader.MI_OK:
                return None
            result = reader.MFRC522_Read(block)
            status, data = result if isinstance(result, tuple) else (reader.MI_OK, result)
            if status != reader.MI_OK or data is None:
                return None
            data = bytes(data)
            return data if len(data) == 16 else None
        finally:
            reader.MFRC522_StopCrypto1()

    def status(self) -> dict[str, object]:
        return {"backend": self.name, "ready": self._reader is not None,
                "bus": self.bus, "device": self.device, "reset_gpio": self.pin_rst}

    def close(self) -> None:
        reader, self._reader = self._reader, None
        if reader is not None:
            reader.MFRC522_StopCrypto1()
            spi = getattr(reader, "spi", None)
            if spi is not None and hasattr(spi, "close"):
                spi.close()

    def __enter__(self) -> "MFRC522Reader":
        self.open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
