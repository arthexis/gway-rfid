import pytest

from gway_rfid.card import BLOCK_SIZE, HEADER_BLOCK, CardFormatError, payload_capacity
from gway_rfid.storage import MemoryBlockTransport, read_payload, write_payload


class CorruptingTransport(MemoryBlockTransport):
    corrupt_block: int

    def __init__(self, corrupt_block: int) -> None:
        super().__init__()
        self.corrupt_block = corrupt_block

    def write_block(self, block: int, data: bytes) -> None:
        super().write_block(block, data)
        if block == self.corrupt_block:
            self.blocks[block] = bytes([data[0] ^ 1]) + data[1:]


def test_write_and_read_use_only_required_payload_blocks() -> None:
    transport = MemoryBlockTransport()
    payload = b"x" * 17

    header = write_payload(transport, payload)
    restored_header, restored = read_payload(transport)

    assert restored == payload
    assert restored_header == header
    assert set(transport.blocks) == {HEADER_BLOCK, 2, 4}


def test_failed_payload_verification_leaves_header_invalid() -> None:
    transport = CorruptingTransport(2)

    with pytest.raises(CardFormatError, match="payload verification"):
        write_payload(transport, b"command")

    assert transport.read_block(HEADER_BLOCK) == bytes(BLOCK_SIZE)


def test_capacity_failure_happens_before_card_mutation() -> None:
    original = b"previous header!".ljust(BLOCK_SIZE, b"!")
    transport = MemoryBlockTransport({HEADER_BLOCK: original})

    with pytest.raises(CardFormatError):
        write_payload(transport, b"x" * (payload_capacity() + 1))

    assert transport.read_block(HEADER_BLOCK) == original
