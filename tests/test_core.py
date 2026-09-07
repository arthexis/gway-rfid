from gway_rfid import Tag, normalize_uid
from gway_rfid.backends import MockReader


def test_normalize_uid_accepts_common_formats():
    assert normalize_uid("04:A1-b2 c3") == bytes.fromhex("04A1B2C3")
    assert normalize_uid(0x04A1B2C3) == bytes.fromhex("04A1B2C3")


def test_tag_uid_hex_is_compact_uppercase():
    tag = Tag(bytes.fromhex("04a1b2c3"), reader="test")
    assert tag.uid_hex == "04A1B2C3"


def test_mock_reader_is_deterministic():
    reader = MockReader(["01", "02"])
    assert reader.scan().uid_hex == "01"
    assert reader.scan().uid_hex == "02"
    assert reader.scan() is None
