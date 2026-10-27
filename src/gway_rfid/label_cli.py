"""Standalone label-printer commands (no Gway registry required)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="gway-rfid", description="Standalone RFID label utilities")
    groups = root.add_subparsers(dest="group", required=True)
    label = groups.add_parser("label", help="Render or print an explicit QR label")
    label_commands = label.add_subparsers(dest="action", required=True)
    for action in ("preview", "print"):
        sub = label_commands.add_parser(action)
        sub.add_argument("--text", required=True, help="Explicit QR payload; never inferred from a card")
        sub.add_argument("--title", default="")
        sub.add_argument("--subtitle", default="")
        sub.add_argument("--footer", default="")
        sub.add_argument("--width", type=int, default=320)
        sub.add_argument("--height", type=int, default=240)
        sub.add_argument("--qr-size", type=int, default=160)
        if action == "preview":
            sub.add_argument("--output", required=True, help="Destination PNG file")
        else:
            sub.add_argument("--printer", choices=["phomemo-m220"], required=True)
            sub.add_argument("--dry-run", action="store_true")
            sub.add_argument("--usb-path", help="Explicit Windows USBPRINT interface")
            sub.add_argument("--speed", type=int, default=2)
            sub.add_argument("--density", type=int, default=15)
            sub.add_argument("--chunk-bytes", type=int, default=16)
            sub.add_argument("--chunk-delay", type=float, default=0.04)
    printer = groups.add_parser("printer", help="Inspect a connected label printer")
    printer_commands = printer.add_subparsers(dest="action", required=True)
    printer_commands.add_parser("devices")
    printer_commands.add_parser("test")
    return root


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        from .printing import (
            QRLabelSpec, build_qr_label_image, build_phomemo_m220_job,
            iter_phomemo_m220_usb_paths, resolve_phomemo_m220_usb_path,
            write_windows_usb,
        )
        if args.group == "printer":
            if args.action == "devices":
                paths = list(iter_phomemo_m220_usb_paths())
                for path in paths:
                    print(path)
                if not paths:
                    print("No Phomemo M220 Windows USBPRINT device detected")
                return 0
            image = build_qr_label_image("PRINTER TEST", QRLabelSpec(title="PRINTER TEST"))
            print(f"PRINTER=phomemo-m220 COMMAND_BYTES={len(build_phomemo_m220_job(image))} DRY_RUN=1")
            return 0
        spec = QRLabelSpec(
            width=args.width, height=args.height, qr_size=args.qr_size,
            title=args.title, subtitle=args.subtitle, footer=args.footer,
        )
        image = build_qr_label_image(args.text, spec)
        if args.action == "preview":
            output = Path(args.output)
            image.save(output, format="PNG")
            print(f"PREVIEW={output}")
            return 0
        job = build_phomemo_m220_job(image, speed=args.speed, density=args.density)
        if args.dry_run:
            print(f"PRINTER=phomemo-m220 COMMAND_BYTES={len(job)} DRY_RUN=1")
            return 0
        path = resolve_phomemo_m220_usb_path(args.usb_path)
        if not path:
            raise ValueError("No Windows USBPRINT path available; pass --usb-path or set ARTHEXIS_QR_PRINTER_USB_PATH")
        written = write_windows_usb(path, job, chunk_size=args.chunk_bytes, delay_seconds=args.chunk_delay)
        print(f"PRINTER=phomemo-m220 WRITTEN={written}")
        return 0
    except (ImportError, OSError, ValueError) as error:
        print(f"gway-rfid: {error}", file=sys.stderr)
        return 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
