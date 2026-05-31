"""W&B Weave instrumentation."""
from __future__ import annotations

import wandb
import weave

from ..config import settings

_initialized = False


def init() -> None:
    """Call once at app startup before any agent runs."""
    global _initialized
    if _initialized:
        return
    wandb.login(key=settings.wandb_api_key)
    weave.init(settings.weave_project_path)
    _initialized = True


def ensure_init() -> None:
    """Idempotent init for CLI paths that skip FastAPI lifespan."""
    init()


def label_trace(call_id: str, outcome: str) -> None:
    """Attach ground-truth outcome to a Weave trace after the match resolves."""
    print(f"[weave] label trace {call_id} → {outcome}")
