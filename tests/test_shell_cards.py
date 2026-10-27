"""Full shell programs are portable, signed data until explicitly executed."""
from __future__ import annotations

import os
import subprocess
from dataclasses import replace
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gway_rfid.card import HEADER_BLOCK, CardFormatError, blocks_for_length, payload_capacity
from gway_rfid.codec import CommandEnvelope, SignatureError, canonical_cbor, decode_signed, sign, encode_signed
from gway_rfid.shell_cards import (
    SIGNING_DOMAIN, ShellProgram, decode_program, encode_program, execute_program,
    read_program, verify_program, write_program,
)
from gway_rfid.storage import MemoryBlockTransport, read_payload, write_payload


@pytest.fixture
def signed():
    key = Ed25519PrivateKey.generate()
    program = ShellProgram("printf '%s\\n' 'one two' | sed 's/two/three/'\nprintf 'α\\n'\n", "ops", "TEST")
    return program, key, encode_program(program, key)


def test_multiline_script_roundtrips_without_local_uid_mapping(signed):
    program, key, payload = signed
    first, second = MemoryBlockTransport(), MemoryBlockTransport()
    for card in (first, second):
        write_program(card, payload)
        header, readback = read_program(card)
        assert header.flags == 1
        assert verify_program(readback, {"ops": key.public_key()}) == program
        assert set(card.blocks) == {HEADER_BLOCK, *blocks_for_length(len(payload))}
    assert first.blocks == second.blocks
    assert payload == encode_program(program, key)


@pytest.mark.parametrize("field,value", [
    ("script", ""), ("script", "  \n"), ("script", "a\0b"), ("script", 7),
    ("script", "\ud800"), ("issuer", "../ops"), ("issuer", ""),
    ("label", "\n"), ("label", "x" * 65), ("timeout", True),
    ("timeout", 0), ("timeout", 301), ("timeout", "30"),
])
def test_invalid_program_fields_rejected_before_signing(signed, field, value):
    with pytest.raises(CardFormatError):
        replace(signed[0], **{field: value})


def test_tampered_untrusted_and_wrong_key_never_execute(signed, monkeypatch):
    program, key, payload = signed
    popen = Mock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    changed = canonical_cbor({**program.unsigned(), "script": "malicious", "sig": decode_program(payload)[1]})
    for data, trusted in ((changed, {"ops": key.public_key()}), (payload, {}),
                           (payload, {"ops": Ed25519PrivateKey.generate().public_key()})):
        with pytest.raises(SignatureError):
            execute_program(data, trusted)
    popen.assert_not_called()


def test_managed_argv_and_shell_signatures_cannot_be_confused(signed):
    program, key, payload = signed
    with pytest.raises(CardFormatError):
        decode_signed(payload)
    with pytest.raises(CardFormatError):
        decode_program(encode_signed(sign(CommandEnvelope(("device", "status")), key)))
    unseparated = canonical_cbor({**program.unsigned(), "sig": key.sign(canonical_cbor(program.unsigned()))})
    with pytest.raises(SignatureError):
        verify_program(unseparated, {"ops": key.public_key()})
    assert SIGNING_DOMAIN


@pytest.mark.parametrize("data", [b"", b"\xff", b"not cbor", canonical_cbor([])])
def test_malformed_data_rejected(data):
    with pytest.raises(CardFormatError):
        decode_program(data)


def test_trailing_noncanonical_and_extra_fields_rejected(signed):
    program, _, payload = signed
    signature = decode_program(payload)[1]
    for candidate in (payload + b"\x00", canonical_cbor({**program.unsigned(), "sig": signature, "argv": []}),
                      canonical_cbor({**program.unsigned(), "sig": b"short"})):
        with pytest.raises(CardFormatError):
            decode_program(candidate)


def test_capacity_preflight_never_invalidates_existing_header(signed):
    program, key, _ = signed
    card = MemoryBlockTransport({HEADER_BLOCK: b"old".ljust(16, b"!")})
    before = dict(card.blocks)
    oversized = encode_program(replace(program, script="x" * payload_capacity()), key)
    with pytest.raises(CardFormatError):
        write_program(card, oversized)
    assert card.blocks == before


def test_failed_write_cannot_leave_a_valid_command(signed):
    class Failing(MemoryBlockTransport):
        def write_block(self, block, data):
            if block == 4:
                raise OSError("card removed")
            super().write_block(block, data)
    card = Failing()
    with pytest.raises(OSError):
        write_program(card, signed[2])
    assert card.read_block(HEADER_BLOCK) == bytes(16)
    with pytest.raises(CardFormatError):
        read_program(card)


def test_flags_and_digest_are_checked(signed):
    card = MemoryBlockTransport()
    write_payload(card, signed[2], flags=0)
    with pytest.raises(CardFormatError, match="not a shell"):
        read_program(card)
    write_program(card, signed[2])
    card.blocks[2] = b"x" * 16
    with pytest.raises(CardFormatError, match="content ID"):
        read_payload(card)


def test_explicit_execution_handles_shell_syntax_with_minimal_environment(signed, tmp_path, monkeypatch):
    _, key, _ = signed
    monkeypatch.setenv("RFID_PRIVATE_TEST_SECRET", "must-not-inherit")
    target = tmp_path / "result.txt"
    program = ShellProgram(f"printf '%s\\n' 'one two' | sed 's/two/three/' > '{target}'\n"
                           "test -z \"${RFID_PRIVATE_TEST_SECRET+x}\"\n", "ops")
    assert execute_program(encode_program(program, key), {"ops": key.public_key()}) == 0
    assert target.read_text() == "one three\n"


def test_root_execution_rejected_before_process_creation(signed, monkeypatch):
    _, key, payload = signed
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    spawn = Mock()
    monkeypatch.setattr(subprocess, "Popen", spawn)
    with pytest.raises(PermissionError, match="root"):
        execute_program(payload, {"ops": key.public_key()})
    spawn.assert_not_called()


def test_timeout_kills_process_group_without_exposing_script(signed, monkeypatch):
    _, key, payload = signed
    process = Mock(pid=54321)
    process.wait.side_effect = [subprocess.TimeoutExpired("/bin/sh", 1), 0]
    spawn, kill = Mock(return_value=process), Mock()
    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(os, "killpg", kill)
    with pytest.raises(RuntimeError, match="timed out"):
        execute_program(payload, {"ops": key.public_key()}, max_timeout=1)
    kill.assert_called_once_with(54321, 9)
    assert spawn.call_args.args[0] == ["/bin/sh", "-s"]
    assert spawn.call_args.kwargs["start_new_session"] is True
    assert process.wait.call_args_list[0].kwargs == {"timeout": 1}


def test_nonzero_shell_exit_is_preserved(signed):
    _, key, _ = signed
    payload = encode_program(ShellProgram("exit 7", "ops"), key)
    assert execute_program(payload, {"ops": key.public_key()}) == 7
