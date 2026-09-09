from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from gway_rfid.card import CardFormatError, content_id

ENVELOPE_VERSION = 1


class SignatureError(CardFormatError):
    """Raised when a command envelope cannot be authenticated."""


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    argv: tuple[str, ...]
    label: str | None = None
    issuer: str | None = None
    version: int = ENVELOPE_VERSION

    def __post_init__(self) -> None:
        if self.version != ENVELOPE_VERSION:
            raise CardFormatError(f"unsupported envelope version: {self.version}")
        if not self.argv or not all(isinstance(arg, str) for arg in self.argv):
            raise CardFormatError("argv must contain at least one string")

    def unsigned_map(self) -> dict[str, Any]:
        data: dict[str, Any] = {"v": self.version, "argv": list(self.argv)}
        if self.label is not None:
            data["label"] = self.label
        if self.issuer is not None:
            data["issuer"] = self.issuer
        return data


@dataclass(frozen=True, slots=True)
class SignedCommand:
    envelope: CommandEnvelope
    signature: bytes

    @property
    def content_id(self) -> int:
        return content_id(encode_signed(self))


def canonical_cbor(value: Any) -> bytes:
    return cbor2.dumps(value, canonical=True)


def signing_bytes(envelope: CommandEnvelope) -> bytes:
    return canonical_cbor(envelope.unsigned_map())


def sign(envelope: CommandEnvelope, private_key: Ed25519PrivateKey) -> SignedCommand:
    return SignedCommand(envelope, private_key.sign(signing_bytes(envelope)))


def verify(command: SignedCommand, public_key: Ed25519PublicKey) -> None:
    try:
        public_key.verify(command.signature, signing_bytes(command.envelope))
    except InvalidSignature as exc:
        raise SignatureError("invalid command signature") from exc


def encode_signed(command: SignedCommand) -> bytes:
    data = command.envelope.unsigned_map()
    data["sig"] = command.signature
    return canonical_cbor(data)


def decode_signed(payload: bytes) -> SignedCommand:
    try:
        data = cbor2.loads(payload)
    except (ValueError, TypeError) as exc:
        raise CardFormatError("invalid command CBOR") from exc
    if not isinstance(data, Mapping):
        raise CardFormatError("command envelope must be a CBOR map")
    if canonical_cbor(data) != payload:
        raise CardFormatError("command envelope is not canonical CBOR")

    allowed = {"v", "argv", "label", "issuer", "sig"}
    if set(data) - allowed:
        raise CardFormatError("command envelope contains unknown fields")
    argv = data.get("argv")
    signature = data.get("sig")
    if not isinstance(argv, Sequence) or isinstance(argv, (str, bytes)):
        raise CardFormatError("argv must be an array of strings")
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise CardFormatError("sig must be a 64-byte Ed25519 signature")

    envelope = CommandEnvelope(
        argv=tuple(argv),
        label=_optional_string(data, "label"),
        issuer=_optional_string(data, "issuer"),
        version=data.get("v", 0),
    )
    return SignedCommand(envelope, signature)


def to_json_dict(command: SignedCommand) -> dict[str, Any]:
    data = command.envelope.unsigned_map()
    data["sig"] = urlsafe_b64encode(command.signature).rstrip(b"=").decode("ascii")
    return data


def from_json_dict(data: Mapping[str, Any]) -> SignedCommand:
    argv = data.get("argv")
    if not isinstance(argv, Sequence) or isinstance(argv, (str, bytes)):
        raise CardFormatError("argv must be an array of strings")
    encoded_signature = data.get("sig")
    if not isinstance(encoded_signature, str):
        raise CardFormatError("sig must be a base64url string")
    try:
        padding = "=" * (-len(encoded_signature) % 4)
        signature = urlsafe_b64decode(encoded_signature + padding)
    except ValueError as exc:
        raise CardFormatError("invalid base64url signature") from exc
    if len(signature) != 64:
        raise CardFormatError("sig must decode to 64 bytes")
    return SignedCommand(
        CommandEnvelope(
            argv=tuple(argv),
            label=_optional_string(data, "label"),
            issuer=_optional_string(data, "issuer"),
            version=data.get("v", 0),
        ),
        signature,
    )


def _optional_string(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise CardFormatError(f"{key} must be a string")
    return value
