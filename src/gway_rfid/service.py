"""Persistent MFRC522 observation service; command execution is not enabled."""
from __future__ import annotations

import argparse
import json
import logging
import signal
import time

from gway_rfid.backends.mfrc522 import MFRC522Reader
from gway_rfid.presence import PresenceTracker

LOG = logging.getLogger("gway_rfid.service")


def run(*, interval: float = 0.15, reader: object | None = None) -> None:
    if interval <= 0:
        raise ValueError("interval must be positive")
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    device = reader if reader is not None else MFRC522Reader()
    tracker = PresenceTracker()
    try:
        device.open()
        LOG.info("RFID reader opened")
        while not stopping:
            for event in tracker.observe(device.scan(), time.monotonic()):
                if event.kind == "scanned":
                    LOG.info("rfid.scanned %s", json.dumps({"uid": event.uid, "generation": event.generation}))
            time.sleep(interval)
    finally:
        device.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Gway RFID observation service")
    parser.add_argument("--interval", type=float, default=0.15)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(interval=args.interval)


if __name__ == "__main__":
    main()
