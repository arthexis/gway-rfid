"""MFRC522 SPI backend extracted from gway-ap-kiosk field revision 1c602d5.

Hardware libraries are imported only when the reader is opened. The
advisory lock prevents concurrent access by cooperating scanner processes.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import Any

from gway_rfid.core import Tag


class MFRC522Reader:
    name = "mfrc522"

    def __init__(self, bus: int = 0, device: int = 0, pin_mode: int = 11, pin_rst: int = 25) -> None:
        self.bus, self.device = bus, device
        self.pin_mode, self.pin_rst = pin_mode, pin_rst
        self._reader: Any | None = None
        self._lock_fd: int | None = None

    def open(self) -> None:
        if self._reader is not None:
            return
        self._acquire_lock()
        try:
            self._assert_device_available()
            import RPi.GPIO as GPIO  # type: ignore[import-not-found]
            from mfrc522 import MFRC522  # type: ignore[import-not-found]

            GPIO.setwarnings(False)
            self._reader = MFRC522(
                bus=self.bus, device=self.device,
                pin_mode=self.pin_mode, pin_rst=self.pin_rst,
            )
        except BaseException:
            self.close()
            raise

    def _acquire_lock(self) -> None:
        """Prevent simultaneous access by cooperating RFID scanner processes."""
        if self._lock_fd is not None:
            return
        path = Path(f"/run/lock/gway-rfid-spi{self.bus}.{self.device}.lock")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(fd)
            raise RuntimeError(f"RFID reader lock is held: {path}") from None
        self._lock_fd = fd

    def _assert_device_available(self) -> None:
        """Require the configured SPI node; concurrency uses the advisory lock.

        Unprivileged services cannot enumerate other users' /proc/*/fd entries.
        Such enumeration caused a permanent restart loop on /proc/1/fd.
        Non-cooperating legacy readers must be disabled during cutover.
        """
        target = Path(f"/dev/spidev{self.bus}.{self.device}")
        if not target.exists():
            raise RuntimeError(f"RFID SPI device unavailable: {target}")

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
        if key_type not in ("A", "B") or len(key) != 6:
            raise ValueError("key_type must be A/B and key must be six bytes")
        if not 0 <= block <= 63:
            raise ValueError("block must be within MIFARE Classic 1K range")
        self.open()
        reader = self._reader
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
        try:
            if reader is not None:
                try:
                    reader.MFRC522_StopCrypto1()
                finally:
                    spi = getattr(reader, "spi", None)
                    if spi is not None and hasattr(spi, "close"):
                        spi.close()
        finally:
            if self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None

    def __enter__(self) -> "MFRC522Reader":
        self.open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
