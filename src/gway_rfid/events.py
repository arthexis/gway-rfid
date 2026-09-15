from __future__ import annotations

import os
from typing import Any

DEFAULT_QUEUE = "rfid.scanned"
DEFAULT_BROKER_ENV = "CELERY_BROKER_URL"


def publish_event(
    event_type: str,
    /,
    *,
    broker_url: str | None = None,
    queue: str = DEFAULT_QUEUE,
    **fields: Any,
) -> bool:
    """Publish a plain JSON event to the selected Kombu queue.

    Queue publication is optional and non-fatal so an RFID scan remains useful even
    when the local broker is unavailable.
    """
    url = (broker_url or os.environ.get(DEFAULT_BROKER_ENV, "")).strip()
    if not url:
        return False

    try:
        from kombu import Connection

        with Connection(url, connect_timeout=1) as connection:
            with connection.SimpleQueue(queue) as destination:
                destination.put(
                    {"type": event_type, **{k: v for k, v in fields.items() if v is not None}},
                    serializer="json",
                )
    except Exception:
        return False
    return True


def publish_scanned(
    record: dict[str, str],
    *,
    broker_url: str | None = None,
    queue: str = DEFAULT_QUEUE,
) -> bool:
    """Publish a normalized RFID scan to the dedicated RFID queue."""
    return publish_event(
        "rfid.scanned",
        broker_url=broker_url,
        queue=queue,
        **record,
    )
