import pytest

from gway_rfid.card import (
    BLOCK_SIZE,
    CardFormatError,
    CardHeader,
    blocks_for_length,
    content_id,
    payload_blocks,
    payload_capacity,
)


def test_header_round_trip() -> None:
    header = CardHeader(payload_length=31, content_id=0x0123456789ABCDEF, flags=3)
    encoded = header.encode()

    assert len(encoded) == BLOCK_SIZE
    assert CardHeader.decode(encoded) == header


def test_payload_layout_skips_sector_trailers() -> None:
    blocks = payload_blocks()

    assert blocks[:5] == (2, 4, 5, 6, 8)
    assert blocks[-3:] == (60, 61, 62)
    assert len(blocks) == 46
    assert payload_capacity() == 736
    assert all(block % 4 != 3 for block in blocks)


def test_blocks_for_length_reads_only_needed_blocks() -> None:
    assert blocks_for_length(0) == ()
    assert blocks_for_length(1) == (2,)
    assert blocks_for_length(16) == (2,)
    assert blocks_for_length(17) == (2, 4)


def test_capacity_is_enforced() -> None:
    with pytest.raises(CardFormatError):
        CardHeader(payload_capacity() + 1, 1).encode()
    with pytest.raises(CardFormatError):
        blocks_for_length(payload_capacity() + 1)


def test_content_id_is_stable_and_content_sensitive() -> None:
    first = content_id(b"canonical envelope")

    assert first == content_id(b"canonical envelope")
    assert first != content_id(b"changed envelope")
