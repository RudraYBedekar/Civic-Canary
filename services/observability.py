from __future__ import annotations

import json
import logging
from typing import Any

LOGGER = logging.getLogger("civic_canary")
LOGGER.setLevel(logging.INFO)


def log_event(event: str, *, run_id: str, **details: Any) -> None:
    """Emit one searchable CloudWatch record without secrets or form values."""
    LOGGER.info(
        json.dumps(
            {"event": event, "run_id": run_id, **details},
            separators=(",", ":"),
            default=str,
        )
    )
