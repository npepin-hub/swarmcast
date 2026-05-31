"""Research ML logging — stdout + logger (uvicorn only shows prints by default)."""
from __future__ import annotations

import json
import logging

from ...config import settings

logger = logging.getLogger(__name__)


def research_ml_log(message: str, *, payload: dict | None = None) -> None:
    line = f"[research-ml] {message}"
    if payload is not None:
        line += " " + json.dumps(payload, default=str)
    if settings.research_log_ml:
        print(line, flush=True)
    else:
        logger.info("%s", line)
