"""Signed, portable POSIX shell programs. Importing/inspecting never executes."""
from __future__ import annotations

import os
import re
import signal
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .card import CardFormatError, CardHeader
from .codec import SignatureError, canonical_cbor
from .storage import BlockTransport, read_payload, write_payload

SHELL_FLAG = 1
SIGNING_DOMAIN = b"gway-rfid:shell:v1\x00"
ISSUER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")


@dataclass(frozen=True)
class ShellProgram:
    script: str
    issuer: str
    label: str = ""
    timeout: int = 30

    def __post_init__(self) -> None:
        if not isinstance(self.script, str) or not self.script.strip() or "\0" in self.script:
            raise CardFormatError("script must be nonempty text without NUL characters")
        if not isinstance(self.issuer, str) or not ISSUER.fullmatch(self.issuer):
            raise CardFormatError("issuer must be 1-32 letters, digits, underscores or hyphens")
        if not isinstance(self.label, str) or len(self.label) > 64 or any(ord(c) < 32 for c in self.label):
            raise CardFormatError("label must be at most 64 printable characters")
        if type(self.timeout) is not int or not 1 <= self.timeout <= 300:
            raise CardFormatError("timeout must be an integer from 1 to 300 seconds")
        try:
            self.script.encode("utf-8")
            self.label.encode("utf-8")
        except UnicodeError as exc:
            raise CardFormatError("script and label must be valid UTF-8") from exc

    def unsigned(self) -> dict[str, object]:
        return {"v": 1, "kind": "shell", "script": self.script,
                "issuer": self.issuer, "label": self.label, "timeout": self.timeout}


def encode_program(program: ShellProgram, key: Ed25519PrivateKey) -> bytes:
    body = program.unsigned()
    return canonical_cbor({**body, "sig": key.sign(SIGNING_DOMAIN + canonical_cbor(body))})


def decode_program(payload: bytes) -> tuple[ShellProgram, bytes]:
    try:
        data = cbor2.loads(payload)
    except (cbor2.CBORDecodeError, ValueError, TypeError) as exc:
        raise CardFormatError("invalid shell-card CBOR") from exc
    fields = {"v", "kind", "script", "issuer", "label", "timeout", "sig"}
    if not isinstance(data, Mapping) or set(data) != fields:
        raise CardFormatError("invalid shell-card envelope fields")
    if type(data["v"]) is not int or data["v"] != 1 or data["kind"] != "shell":
        raise CardFormatError("unsupported shell-card envelope")
    if canonical_cbor(data) != payload:
        raise CardFormatError("shell-card envelope must use canonical CBOR")
    signature = data["sig"]
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise SignatureError("shell-card signature must be 64 bytes")
    program = ShellProgram(data["script"], data["issuer"], data["label"], data["timeout"])
    return program, signature


def verify_program(payload: bytes, trusted: Mapping[str, Ed25519PublicKey]) -> ShellProgram:
    program, signature = decode_program(payload)
    key = trusted.get(program.issuer)
    if not isinstance(key, Ed25519PublicKey):
        raise SignatureError("shell-card issuer is not trusted")
    try:
        key.verify(signature, SIGNING_DOMAIN + canonical_cbor(program.unsigned()))
    except InvalidSignature as exc:
        raise SignatureError("invalid shell-card signature") from exc
    return program


def read_program(transport: BlockTransport) -> tuple[CardHeader, bytes]:
    header, payload = read_payload(transport)
    if header.flags != SHELL_FLAG:
        raise CardFormatError("card is not a shell program")
    decode_program(payload)
    return header, payload


def write_program(transport: BlockTransport, payload: bytes) -> CardHeader:
    decode_program(payload)
    return write_payload(transport, payload, flags=SHELL_FLAG)


def load_private_key(path: Path) -> Ed25519PrivateKey:
    # The CLI never receives a plaintext key through argv or prints key material.
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("signing key must be Ed25519")
    return key


def load_trust(directory: Path) -> dict[str, Ed25519PublicKey]:
    trusted = {}
    for path in sorted(directory.glob("*.pem")):
        if not ISSUER.fullmatch(path.stem):
            raise ValueError("invalid trusted issuer filename")
        key = serialization.load_pem_public_key(path.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("trusted issuer key must be Ed25519")
        trusted[path.stem] = key
    if not trusted:
        raise SignatureError("no trusted shell-card issuers configured")
    return trusted


def execute_program(payload: bytes, trusted: Mapping[str, Ed25519PublicKey], *,
                    max_timeout: int = 30) -> int:
    """Explicit trusted-code execution, not a sandbox or implicit scanner hook.

    Commands receive only PATH and locale, never the caller's credential-bearing
    environment. Descendants remaining in the command process group are killed
    after completion as well as timeout. Scripts may still access the account's
    files/network; a trusted issuer is authorized to run arbitrary account code.
    """
    program = verify_program(payload, trusted)
    if os.name != "posix":
        raise RuntimeError("shell-card execution requires POSIX process groups")
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("shell-card execution as root is prohibited")
    if type(max_timeout) is not int or not 1 <= max_timeout <= 300:
        raise ValueError("max_timeout must be an integer from 1 to 300")
    # A seekable file avoids both pipe deadlocks and command text in process argv.
    import tempfile
    with tempfile.TemporaryFile() as stream:
        stream.write(program.script.encode("utf-8"))
        stream.seek(0)
        process = subprocess.Popen(
            ["/bin/sh", "-s"], stdin=stream, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, cwd="/", start_new_session=True,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        try:
            return process.wait(timeout=min(program.timeout, max_timeout))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("shell-card execution timed out") from exc
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
