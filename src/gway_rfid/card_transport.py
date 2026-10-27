"""Block transports for shell-card tools; no device opens on import."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from .card import BLOCK_SIZE, MAX_BLOCK, CardFormatError, is_trailer_block

IMAGE_SIZE = (MAX_BLOCK + 1) * BLOCK_SIZE


class CardImage:
    """Exact 1K image, persisted block-by-block like physical card memory."""

    def __init__(self, path: Path, *, writable: bool = False, overwrite: bool = False):
        flags = os.O_RDWR if writable else os.O_RDONLY
        if writable:
            flags |= os.O_CREAT
            if not overwrite:
                flags |= os.O_EXCL
        fd = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), 0o600)
        self.stream = os.fdopen(fd, "r+b" if writable else "rb")
        try:
            size = os.fstat(fd)
            if not stat.S_ISREG(size.st_mode):
                raise CardFormatError("card image must be a regular file")
            if size.st_size == 0 and writable:
                self.stream.write(bytes(IMAGE_SIZE))
                self.stream.flush()
            elif size.st_size != IMAGE_SIZE:
                raise CardFormatError("card image must contain exactly 1024 bytes")
        except BaseException:
            self.close()
            raise

    def read_block(self, block: int) -> bytes:
        if not 0 <= block <= MAX_BLOCK:
            raise ValueError("invalid card block")
        self.stream.seek(block * BLOCK_SIZE)
        return self.stream.read(BLOCK_SIZE)

    def write_block(self, block: int, data: bytes) -> None:
        if not 1 <= block <= MAX_BLOCK or is_trailer_block(block):
            raise ValueError("cannot write manufacturer or trailer blocks")
        if len(data) != BLOCK_SIZE:
            raise ValueError("card blocks must be 16 bytes")
        self.stream.seek(block * BLOCK_SIZE)
        self.stream.write(data)
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self) -> None:
        self.stream.close()


class SelectedCard:
    """Use one selected UID and configured key, never blind key probing."""

    def __init__(self, reader, uid: bytes, *, key: bytes, key_type: str = "A"):
        if len(key) != 6 or key_type not in ("A", "B"):
            raise ValueError("card key must be six bytes with type A or B")
        self.reader, self.uid = reader, uid
        self.key, self.key_type = key, key_type

    def read_block(self, block: int) -> bytes:
        data = self.reader.read_block(block, self.uid, key_type=self.key_type, key=self.key)
        if data is None:
            raise CardFormatError("card block read/authentication failed")
        return data

    def write_block(self, block: int, data: bytes) -> None:
        self.reader.write_block(block, data, self.uid, key_type=self.key_type, key=self.key)
