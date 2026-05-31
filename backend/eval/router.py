"""FastAPI router for /history evaluation page."""
from __future__ import annotations
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

log = logging.getLogger(__name__)

from ..observability.weave_tracer import ensure_init
from .wc_backtest import _FALLBACK_MATCHES, _load_from_disk, judge_prediction, sample_2022
from .weave_eval import SwarmCastPredictor

router = APIRouter()


@router.get("/history")
async def history_page():
    return FileResponse("frontend/history.html")


@router.get("/history/matches")
async def history_matches():
    """Return matches for the initial page render — no live API call.

    Priority: disk cache (saved by a previous eval run) → static fallback.
    The live API is called when the user runs an evaluation via /history/ws,
    which updates the disk cache so the next page load reflects real data.
    """
    matches = _load_from_disk() or list(_FALLBACK_MATCHES)
    return [
        {
            "match_id": m.match_id, "team_a": m.team_a, "team_b": m.team_b,
            "stage": m.stage, "actual_winner": m.actual_winner,
            "score": m.score, "group": m.group,
        }
        for m in matches
    ]


async def _ws_send(ws: WebSocket, lock: asyncio.Lock, payload: dict) -> bool:
    """Serialised send — returns False if socket is already closed."""
    async with lock:
        try:
            await ws.send_json(payload)
            return True
        except (WebSocketDisconnect, RuntimeError):
            return False


@router.websocket("/history/ws")
async def history_ws(ws: WebSocket, seed: int = 42):
    await ws.accept()
    lock = asyncio.Lock()
    try:
        # Resolve match list (disk cache → fallback → live API)
        matches = await asyncio.to_thread(sample_2022, seed)

        if not await _ws_send(ws, lock, {"type": "matches", "data": [
            {"match_id": m.match_id, "team_a": m.team_a, "team_b": m.team_b,
             "stage": m.stage, "actual_winner": m.actual_winner,
             "score": m.score, "group": m.group}
            for m in matches
        ]}):
            return

        ensure_init()
        predictor = SwarmCastPredictor(model_name=f"swarmcast-seed{seed}")
        correct_total = 0

        # Sequential predictions — each result streams to the browser immediately
        for i, match in enumerate(matches):
            if not await _ws_send(ws, lock, {
                "type": "running", "match_id": match.match_id,
            }):
                return

            result = await predictor.predict(
                match_id=match.match_id,
                team_a=match.team_a,
                team_b=match.team_b,
                stage=match.stage,
                group=match.group,
                actual_winner=match.actual_winner,
            )

            # History page always has known winners — always score here
            verdict = judge_prediction(
                result["probability"],
                match.actual_winner,
                match.team_a,
                match.team_b,
                match.stage,
            )

            evaluated = i + 1
            if verdict["correct"]:
                correct_total += 1

            if not await _ws_send(ws, lock, {
                "type": "result",
                "accuracy_so_far": correct_total / evaluated,
                "done": evaluated == len(matches),
                **result,
                **verdict,
            }):
                return

        await _ws_send(ws, lock, {
            "type": "complete",
            "accuracy": correct_total / len(matches) if matches else 0,
        })

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as exc:
        log.exception("history_ws error: %s", exc)
        await _ws_send(ws, lock, {"type": "error", "match_id": "", "message": str(exc)})
