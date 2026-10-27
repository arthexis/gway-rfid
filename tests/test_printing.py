"""Hardware-free regression coverage for legacy-compatible printing."""
from io import BytesIO

import pytest

from gway_rfid import label_cli
from gway_rfid.printing import (
    QRLabelSpec, build_phomemo_m220_job, build_qr_label_image,
    pack_monochrome_raster, render_qr_png_bytes,
)


def test_raster_packs_most_significant_bit_first():
    from PIL import Image
    im = Image.new("L", (8, 1), 255)
    im.putpixel((0, 0), 0)
    im.putpixel((7, 0), 0)
    assert pack_monochrome_raster(im) == (1, 1, bytes([0x81]))


def test_m220_raster_job_framing():
    from PIL import Image
    im = Image.new("1", (8, 1), 1)
    im.putpixel((0, 0), 0)
    job = build_phomemo_m220_job(im, speed=2, density=15)
    assert job.startswith(b"\\1b\\4e\\0d\\02\\1b\\4e\\04\\0f\\1f\\11\\0a")
    assert b"\\1d\\76\\30\\00\\01\\00\\01\\00\\80" in job
    assert job.endswith(b"\\1f\\f0\\05\\00\\1f\\f0\\03\\00")


def test_preview_png_and_layout():
    data = render_qr_png_bytes("PUBLIC TEST", QRLabelSpec(title="PUBLIC TEST"))
    from PIL import Image
    image = Image.open(BytesIO(data))
    assert image.size == (320, 240)
    assert image.format == "PNG"


def test_invalid_label_dimensions():
    with pytest.raises(ValueError, match="divisible by 8"):
        build_qr_label_image("test", QRLabelSpec(width=321))


def test_cli_preview_and_dry_run(tmp_path, capsys):
    dest = tmp_path / "label.png"
    assert label_cli.run(["label", "preview", "--text", "EXPLICIT", "--output", str(dest)]) == 0
    assert dest.is_file()
    assert label_cli.run(["label", "print", "--text", "EXPLICIT", "--printer", "phomemo-m220", "--dry-run"]) == 0
    assert "DRY_RUN=1" in capsys.readouterr().out


def test_cli_mock_printer_test(capsys):
    assert label_cli.run(["printer", "test"]) == 0
    assert "DRY_RUN=1" in capsys.readouterr().out


def test_no_hardware_write_on_non_windows(monkeypatch):
    import gway_rfid.printing as printing
    monkeypatch.setattr(printing.sys, "platform", "linux")
    with pytest.raises(OSError, match="only supported on Windows"):
        printing.write_windows_usb("not-a-printer", b"123")


def test_cli_requires_explicit_print_payload_and_printer():
    with pytest.raises(SystemExit):
        label_cli.parser().parse_args(["label", "print", "--text", "X"])
    with pytest.raises(SystemExit):
        label_cli.parser().parse_args(["label", "print", "--printer", "phomemo-m220"])
