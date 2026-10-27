"""Explicit signed shell-card write, inspect and run commands."""
from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from pathlib import Path

from .card import payload_capacity
from .card_transport import CardImage, SelectedCard
from .shell_cards import (
    ShellProgram, decode_program, encode_program, execute_program,
    load_private_key, load_trust, read_program, verify_program, write_program,
)


def add_commands(groups) -> None:
    command = groups.add_parser("command", help="Write, inspect or explicitly run signed shell cards")
    commands = command.add_subparsers(dest="action", required=True)
    for action in ("write", "inspect", "run"):
        sub = commands.add_parser(action)
        target = sub.add_mutually_exclusive_group(required=True)
        target.add_argument("--image", type=Path, help="Exact 1K card image")
        target.add_argument("--reader", choices=["mfrc522"], help="Exclusively acquire the physical reader")
        sub.add_argument("--card-key-file", type=Path, help="Raw six-byte card access key; default factory key")
        sub.add_argument("--card-key-type", choices=["A", "B"], default="A")
        if action == "write":
            sub.add_argument("--script-file", type=Path, required=True, help="UTF-8 POSIX shell program")
            sub.add_argument("--signing-key", type=Path, required=True, help="Ed25519 private PEM file")
            sub.add_argument("--issuer", required=True)
            sub.add_argument("--label", default="")
            sub.add_argument("--timeout", type=int, default=30)
            sub.add_argument("--overwrite", action="store_true", help="Replace an existing image or physical card contents")
        else:
            sub.add_argument("--trusted-issuers", type=Path, required=action == "run",
                             help="Directory containing <issuer>.pem public keys")
            if action == "inspect":
                sub.add_argument("--show-script", action="store_true", help="Explicitly include the complete script in inspection JSON")
            else:
                sub.add_argument("--max-timeout", type=int, default=30)


@contextmanager
def transport(args):
    if args.image is not None:
        image = CardImage(args.image, writable=args.action == "write",
                          overwrite=getattr(args, "overwrite", False))
        try:
            yield image
        finally:
            image.close()
        return
    if args.action == "write" and not args.overwrite:
        raise ValueError("physical command writes require --overwrite and a disposable card")
    key = args.card_key_file.read_bytes() if args.card_key_file else b"\xff" * 6
    if len(key) != 6:
        raise ValueError("card access key file must contain exactly six bytes")
    from .backends.mfrc522 import MFRC522Reader
    with MFRC522Reader() as reader:
        tag = reader.scan()
        if tag is None:
            raise RuntimeError("no card present; place a card and retry")
        yield SelectedCard(reader, tag.uid, key=key, key_type=args.card_key_type)


def run(args: argparse.Namespace) -> int:
    if args.action == "write":
        program = ShellProgram(args.script_file.read_bytes().decode("utf-8"),
                               args.issuer, args.label, args.timeout)
        key = load_private_key(args.signing_key)
        payload = encode_program(program, key)
        # All format/signature/capacity checks precede device access or image creation.
        if len(payload) > payload_capacity():
            raise ValueError("signed shell program exceeds card capacity")
        verify_program(payload, {program.issuer: key.public_key()})
        with transport(args) as card:
            write_program(card, payload)
            header, readback = read_program(card)
            if readback != payload:
                raise ValueError("shell-card readback differs from signed program")
        print(json.dumps({"written": True, "payload_bytes": header.payload_length,
                          "capacity_bytes": payload_capacity()}))
        return 0
    trusted = load_trust(args.trusted_issuers) if args.trusted_issuers else None
    with transport(args) as card:
        header, payload = read_program(card)
    if args.action == "run":
        returncode = execute_program(payload, trusted, max_timeout=args.max_timeout)
        print(json.dumps({"executed": True, "returncode": returncode}))
        return returncode if 0 <= returncode <= 255 else 1
    program = verify_program(payload, trusted) if trusted is not None else decode_program(payload)[0]
    result = {"kind": "shell", "issuer": program.issuer, "label": program.label,
              "timeout": program.timeout, "verified": trusted is not None,
              "payload_bytes": header.payload_length}
    if args.show_script:
        result["script"] = program.script
    print(json.dumps(result, ensure_ascii=True))
    return 0
