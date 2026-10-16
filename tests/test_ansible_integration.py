"""Exercise a real Ansible install twice, without touching the host's systemd."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_ansible_fresh_install_and_repeat(tmp_path: Path) -> None:
    prefix = tmp_path / "rfid"
    cmd = [
        "ansible-playbook",
        str(ROOT / "ansible/playbooks/install.yml"),
        "-i", "localhost,",
        "-c", "local",
        "-e", f"rfid_prefix={prefix}",
        "-e", "rfid_install_hardware=false",
        "-e", "rfid_manage_service=false",
    ]
    sha = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    release = prefix / "releases" / sha
    current = prefix / "current"

    def install() -> str:
        result = subprocess.run(
            cmd, cwd=ROOT, text=True, capture_output=True,
            timeout=240, check=False, env=os.environ.copy()
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    install()
    assert current.is_symlink()
    assert current.resolve() == release.resolve()
    python = release / "venv/bin/python"
    assert python.is_file()
    subprocess.run(
        [str(python), "-c", "import gway_rfid; import gway_rfid.service"],
        check=True, timeout=30
    )
    first_target = current.resolve()
    install()
    assert current.resolve() == first_target
    assert python.is_file()
    assert not (prefix / "releases" / "legacy").exists()
