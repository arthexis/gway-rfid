"""Regression tests for cooperative MFRC522 ownership."""
import os
import signal
import subprocess
from unittest.mock import Mock, patch

import pytest

from gway_rfid.command_cli import exclusive_reader_window


def test_exclusive_window_pauses_and_resumes_observer(tmp_path):
    reader = Mock()
    reader._acquire_lock.return_value = None
    reader.close.return_value = None
    with patch("gway_rfid.command_cli.os.open", return_value=71), \
         patch("gway_rfid.command_cli.os.close"), \
         patch("gway_rfid.command_cli.fcntl.flock"), \
         patch("gway_rfid.command_cli.subprocess.run", return_value=Mock(stdout="123\\n")), \
         patch("gway_rfid.command_cli.os.kill") as kill, \
         patch("gway_rfid.backends.mfrc522.MFRC522Reader", return_value=reader):
        with exclusive_reader_window():
            pass
    assert kill.call_args_list == [
        ((123, signal.SIGUSR1),),
        ((123, signal.SIGUSR2),),
    ]


def test_exclusive_window_resumes_after_exception():
    reader = Mock()
    with patch("gway_rfid.command_cli.os.open", return_value=71), \
         patch("gway_rfid.command_cli.os.close"), \
         patch("gway_rfid.command_cli.fcntl.flock"), \
         patch("gway_rfid.command_cli.subprocess.run", return_value=Mock(stdout="123\\n")), \
         patch("gway_rfid.command_cli.os.kill") as kill, \
         patch("gway_rfid.backends.mfrc522.MFRC522Reader", return_value=reader):
        with pytest.raises(ValueError):
            with exclusive_reader_window():
                raise ValueError("write failed")
    assert kill.call_args_list[-1].args == (123, signal.SIGUSR2)


def test_exclusive_window_rejects_competing_writer():
    with patch("gway_rfid.command_cli.os.open", return_value=71), \
         patch("gway_rfid.command_cli.os.close"), \
         patch("gway_rfid.command_cli.fcntl.flock", side_effect=BlockingIOError), \
         patch("gway_rfid.command_cli.subprocess.run") as systemctl:
        with pytest.raises(BlockingIOError):
            with exclusive_reader_window():
                pass
    systemctl.assert_not_called()
