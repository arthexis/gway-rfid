from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

MAGIC = b"GWY1"
VERSION = 1
BLOCK_SIZE = 16
HEADER_BLOCK = 1
HEADER_STRUCT = struct.Struct(">4sBBHQ")
MAX_BLOCK = 63


class CardFormatError(ValueError):
    """Raised when GWY1 card data is malformed."""


@dataclass(frozen=True, slots=True)
class CardHeader:
    payload_length: int
    content_id: int
    flags: int = 0
    version: int = VERSION

    def encode(self) -> bytes:
        if not 0 <= self.flags <= 0xFF:
            raise CardFormatError("flags must fit in one byte")
        if not 0 <= self.payload_length <= payload_capacity():
            raise CardFormatError("payload does not fit on a MIFARE Classic 1K card")
        if not 0 <= self.content_id <= 0xFFFFFFFFFFFFFFFF:
            raise CardFormatError("content_id must fit in 64 bits")
        return HEADER_STRUCT.pack(
            MAGIC, self.version, self.flags, self.payload_length, self.content_id
        )

    @classmethod
    def decode(cls, data: bytes) -> CardHeader:
        if len(data) != BLOCK_SIZE:
            raise CardFormatError("GWY1 header must be exactly 16 bytes")
        magic, version, flags, payload_length, content_id = HEADER_STRUCT.unpack(data)
        if magic != MAGIC:
            raise CardFormatError("not a GWY1 card")
        if version != VERSION:
            raise CardFormatError(f"unsupported GWY1 version: {version}")
        if payload_length > payload_capacity():
            raise CardFormatError("declared payload exceeds card capacity")
        return cls(payload_length, content_id, flags, version)


def is_trailer_block(block: int) -> bool:
    return block % 4 == 3


def payload_blocks() -> tuple[int, ...]:
    return tuple(
        block for block in range(2, MAX_BLOCK + 1) if not is_trailer_block(block)
    )


def payload_capacity() -> int:
    return len(payload_blocks()) * BLOCK_SIZE


def blocks_for_length(length: int) -> tuple[int, ...]:
    if length < 0:
        raise ValueError("length cannot be negative")
    if length > payload_capacity():
        raise CardFormatError("payload does not fit on a MIFARE Classic 1K card")
    count = (length + BLOCK_SIZE - 1) // BLOCK_SIZE
    return payload_blocks()[:count]


def content_id(payload: bytes) -> int:
    """Return the GWY1 64-bit content identifier for canonical signed bytes."""
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
