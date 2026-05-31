"""App-wide logging — ensures research-ml and agent logs appear under uvicorn."""
from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
    else:
        logging.basicConfig(
            level=level,
            format="%(levelname)s:%(name)s:%(message)s",
            stream=sys.stderr,
        )
    for name in (
        "backend",
        "backend.agents",
        "backend.agents.research",
        "backend.agents.research.wc_model",
        "backend.agents.research.nodes",
        "backend.agents.research.mcp_features",
    ):
        logging.getLogger(name).setLevel(level)
