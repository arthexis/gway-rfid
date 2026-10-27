"""Public standalone CLI, card images and non-executing inspection."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gway_rfid import command_cli
from gway_rfid.label_cli import run


@pytest.fixture
def material(tmp_path):
    key = Ed25519PrivateKey.generate()
    private = tmp_path / "private.pem"
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    trust = tmp_path / "trusted"
    trust.mkdir()
    (trust / "ops.pem").write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    script = tmp_path / "program.sh"
    script.write_text("printf '%s\\n' 'hello world'\nexit 0\n")
    image = tmp_path / "card.bin"
    arguments = ["command", "write", "--image", str(image), "--script-file", str(script),
                 "--signing-key", str(private), "--issuer", "ops"]
    return image, script, trust, arguments


def test_write_inspect_and_explicit_run_without_printing_dependencies(material, monkeypatch, capsys):
    image, script, trust, arguments = material
    assert run(arguments) == 0
    assert image.stat().st_size == 1024
    assert image.stat().st_mode & 0o777 == 0o600
    capsys.readouterr()
    execute = Mock(return_value=0)
    monkeypatch.setattr(command_cli, "execute_program", execute)
    assert run(["command", "inspect", "--image", str(image)]) == 0
    public = json.loads(capsys.readouterr().out)
    assert public["verified"] is False and "script" not in public
    execute.assert_not_called()
    assert run(["command", "inspect", "--image", str(image), "--trusted-issuers", str(trust), "--show-script"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["verified"] is True and inspected["script"] == script.read_text()
    execute.assert_not_called()
    assert run(["command", "run", "--image", str(image), "--trusted-issuers", str(trust)]) == 0
    assert execute.call_count == 1


def test_existing_image_requires_overwrite_and_keeps_previous_contents(material):
    image, script, _, arguments = material
    assert run(arguments) == 0
    before = image.read_bytes()
    script.write_text("exit 4\n")
    assert run(arguments) == 1
    assert image.read_bytes() == before
    assert run([*arguments, "--overwrite"]) == 0
    assert image.read_bytes() != before


def test_oversized_program_never_opens_image_or_reader(material, monkeypatch):
    image, script, _, arguments = material
    script.write_text("x" * 2000)
    access = Mock()
    monkeypatch.setattr(command_cli, "transport", access)
    assert run(arguments) == 1
    assert not image.exists()
    access.assert_not_called()


def test_missing_trust_or_wrong_key_never_executes(material, monkeypatch):
    image, _, trust, arguments = material
    assert run(arguments) == 0
    execute = Mock()
    monkeypatch.setattr(command_cli, "execute_program", execute)
    for entry in trust.glob("*.pem"):
        entry.unlink()
    assert run(["command", "run", "--image", str(image), "--trusted-issuers", str(trust)]) == 1
    execute.assert_not_called()


def test_run_requires_explicit_trust_directory(material):
    with pytest.raises(SystemExit):
        run(["command", "run", "--image", str(material[0])])


def test_invalid_image_cannot_execute(tmp_path):
    image = tmp_path / "bad.bin"
    image.write_bytes(b"bad")
    assert run(["command", "inspect", "--image", str(image)]) == 1


def test_physical_write_requires_explicit_overwrite_before_reader_access(material, monkeypatch):
    _, _, _, arguments = material
    import gway_rfid.backends.mfrc522 as backend
    reader = Mock()
    monkeypatch.setattr(backend, "MFRC522Reader", reader)
    physical = [value for value in arguments]
    index = physical.index("--image")
    physical[index:index + 2] = ["--reader", "mfrc522"]
    assert run(physical) == 1
    reader.assert_not_called()


def test_script_line_endings_and_utf8_are_preserved(material, capsys):
    image, script, _, arguments = material
    source = "printf 'α\\n'\r\nprintf 'second'\n"
    script.write_bytes(source.encode("utf-8"))
    assert run(arguments) == 0
    capsys.readouterr()
    assert run(["command", "inspect", "--image", str(image), "--show-script"]) == 0
    assert json.loads(capsys.readouterr().out)["script"] == source


def test_complete_cli_roundtrip_executes_card_content(material, tmp_path, capsys):
    image, script, trust, arguments = material
    artifact = tmp_path / "executed.txt"
    script.write_text(f"printf '%s\\n' 'from card' | tr a-z A-Z > '{artifact}'\n")
    assert run(arguments) == 0
    script.unlink()  # Execution must not consult the writer's original file.
    assert run(["command", "run", "--image", str(image), "--trusted-issuers", str(trust)]) == 0
    assert artifact.read_text() == "FROM CARD\n"
    output = capsys.readouterr().out
    assert "printf" not in output and "from card" not in output
    assert json.loads(output.splitlines()[-1]) == {"executed": True, "returncode": 0}
