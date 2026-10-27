"""Image and selected-card adapters enforce block boundaries without hardware."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from gway_rfid.card import CardFormatError
from gway_rfid.card_transport import CardImage, SelectedCard


def test_image_persists_blocks_and_refuses_protected_writes(tmp_path):
    path = tmp_path / "card.bin"
    image = CardImage(path, writable=True)
    try:
        image.write_block(2, b"x" * 16)
        for block in (0, 3, 63, 64, -1):
            with pytest.raises(ValueError):
                image.write_block(block, bytes(16))
        with pytest.raises(ValueError):
            image.write_block(2, b"short")
    finally:
        image.close()
    restored = CardImage(path)
    try:
        assert restored.read_block(2) == b"x" * 16
        assert restored.read_block(1) == bytes(16)
    finally:
        restored.close()


def test_image_size_and_symlinks_are_rejected_without_mutation(tmp_path):
    path = tmp_path / "card.bin"
    path.write_bytes(b"original")
    with pytest.raises(CardFormatError):
        CardImage(path, writable=True, overwrite=True)
    assert path.read_bytes() == b"original"
    alias = tmp_path / "alias.bin"
    alias.symlink_to(path)
    with pytest.raises(OSError):
        CardImage(alias, writable=True, overwrite=True)
    assert path.read_bytes() == b"original"


def test_selected_card_uses_only_configured_uid_and_key():
    reader = Mock()
    reader.read_block.return_value = b"x" * 16
    card = SelectedCard(reader, b"test", key=b"123456", key_type="B")
    assert card.read_block(1) == b"x" * 16
    reader.read_block.assert_called_once_with(1, b"test", key_type="B", key=b"123456")
    card.write_block(2, b"x" * 16)
    reader.write_block.assert_called_once_with(2, b"x" * 16, b"test", key_type="B", key=b"123456")
    reader.read_block.return_value = None
    with pytest.raises(CardFormatError):
        card.read_block(1)
