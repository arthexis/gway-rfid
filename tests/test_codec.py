import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gway_rfid.card import CardFormatError
from gway_rfid.codec import (
    CommandEnvelope,
    SignatureError,
    decode_signed,
    encode_signed,
    from_json_dict,
    sign,
    to_json_dict,
    verify,
)


def test_signed_envelope_round_trip_is_deterministic() -> None:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    envelope = CommandEnvelope(
        ("device", "examine", "[network interface]"),
        label="AUTO EXAM",
        issuer="operations",
    )
    command = sign(envelope, private_key)

    payload = encode_signed(command)
    decoded = decode_signed(payload)

    assert decoded == command
    assert encode_signed(decoded) == payload
    verify(decoded, private_key.public_key())


def test_tampering_is_rejected_by_signature() -> None:
    private_key = Ed25519PrivateKey.generate()
    command = sign(CommandEnvelope(("device", "examine", "eth0")), private_key)
    tampered = type(command)(CommandEnvelope(("device", "examine", "wlan0")), command.signature)

    with pytest.raises(SignatureError):
        verify(tampered, private_key.public_key())


def test_json_is_human_interchange_not_wire_encoding() -> None:
    private_key = Ed25519PrivateKey.generate()
    command = sign(CommandEnvelope(("lcd", "write", "héllo"), issuer="ops"), private_key)

    restored = from_json_dict(to_json_dict(command))

    assert restored == command
    assert encode_signed(restored) == encode_signed(command)


def test_argv_must_be_nonempty_strings() -> None:
    with pytest.raises(CardFormatError):
        CommandEnvelope(())
    with pytest.raises(CardFormatError):
        CommandEnvelope(("device", 3))  # type: ignore[arg-type]
