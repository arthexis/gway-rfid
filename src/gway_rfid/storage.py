from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from gway_rfid.card import (
    BLOCK_SIZE,
    HEADER_BLOCK,
    CardFormatError,
    CardHeader,
    blocks_for_length,
    content_id,
)

INVALID_HEADER = bytes(BLOCK_SIZE)


class BlockTransport(Protocol):
    def read_block(self, block: int) -> bytes: ...

    def write_block(self, block: int, data: bytes) -> None: ...


@dataclass(slots=True)
class MemoryBlockTransport:
    blocks: dict[int, bytes] = field(default_factory=dict)

    def read_block(self, block: int) -> bytes:
        return self.blocks.get(block, bytes(BLOCK_SIZE))

    def write_block(self, block: int, data: bytes) -> None:
        if len(data) != BLOCK_SIZE:
            raise ValueError("RFID blocks must be exactly 16 bytes")
        self.blocks[block] = bytes(data)


def read_payload(transport: BlockTransport) -> tuple[CardHeader, bytes]:
    header = CardHeader.decode(transport.read_block(HEADER_BLOCK))
    chunks = [transport.read_block(block) for block in blocks_for_length(header.payload_length)]
    if any(len(chunk) != BLOCK_SIZE for chunk in chunks):
        raise CardFormatError("reader returned an invalid block length")
    payload = b"".join(chunks)[: header.payload_length]
    if content_id(payload) != header.content_id:
        raise CardFormatError("payload content ID does not match header")
    return header, payload


def write_payload(
    transport: BlockTransport,
    payload: bytes,
    *,
    flags: int = 0,
) -> CardHeader:
    blocks = blocks_for_length(len(payload))
    header = CardHeader(len(payload), content_id(payload), flags)

    # A valid GWY1 header is the commit marker. Invalidate it before mutation.
    transport.write_block(HEADER_BLOCK, INVALID_HEADER)
    if transport.read_block(HEADER_BLOCK) != INVALID_HEADER:
        raise CardFormatError("failed to invalidate card header")

    for index, block in enumerate(blocks):
        start = index * BLOCK_SIZE
        chunk = payload[start : start + BLOCK_SIZE].ljust(BLOCK_SIZE, b"\0")
        transport.write_block(block, chunk)
        if transport.read_block(block) != chunk:
            raise CardFormatError(f"payload verification failed at block {block}")

    encoded_header = header.encode()
    transport.write_block(HEADER_BLOCK, encoded_header)
    if transport.read_block(HEADER_BLOCK) != encoded_header:
        raise CardFormatError("header verification failed")
    return header
