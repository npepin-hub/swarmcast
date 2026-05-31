"""FastAPI app — /forecast + WebSocket."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import weave
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agents.pipeline import run_deliberation
from .config import settings
from .data.wc26 import build_context_bundle, get_groups_data
from .market.edge import detect_and_act
from .market.gamma import find_wc_market
from .observability import weave_tracer
from .schemas import ForecastResult, WSEventType, WSMessage


@asynccontextmanager
async def lifespan(app: FastAPI):
    weave_tracer.init()
    yield


app = FastAPI(title="SwarmCast", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="frontend"), name="static")


class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.remove(ws)

    async def broadcast(self, msg: WSMessage):
        for ws in list(self._connections):
            try:
                await ws.send_text(msg.model_dump_json())
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()


class ForecastRequest(BaseModel):
    match_query: str
    team_a: str
    team_b: str
    team_a_id: int = 0
    team_b_id: int = 0
    competition_id: str = ""
    polymarket_market_id: str = ""


@weave.op()
def run_market_validation(
    consensus_probability: float,
    team_a: str,
    team_b: str,
    polymarket_market_id: str,
):
    try:
        market_id = polymarket_market_id or find_wc_market(team_a, team_b) or ""
        if not market_id:
            return None, None, False, None
        return detect_and_act(consensus_probability, market_id)
    except Exception as exc:
        print(f"[market] validation skipped: {exc}")
        return None, None, False, None


@weave.op()
async def run_forecast_pipeline(req: ForecastRequest) -> ForecastResult:
    async def emit(event: WSEventType, payload):
        await manager.broadcast(WSMessage(event=event, payload=payload))

    contexts = await build_context_bundle(req.team_a, req.team_b, req.competition_id)
    result = await run_deliberation(
        req.match_query,
        req.team_a,
        req.team_b,
        contexts,
        emit=emit,
    )

    forecast = ForecastResult(
        match_query=req.match_query,
        consensus=result.consensus,
        critique=result.critique,
        market=None,
        spread=None,
        edge_detected=False,
        bet_receipt=None,
    )

    snapshot, spread, edge_detected, bet_receipt = await asyncio.to_thread(
        run_market_validation,
        forecast.consensus.probability,
        req.team_a,
        req.team_b,
        req.polymarket_market_id,
    )
    if snapshot is not None or edge_detected:
        await emit(WSEventType.market_check, {
            "snapshot": snapshot.model_dump() if snapshot else None,
            "spread": spread,
        })
        await emit(WSEventType.edge_result, {
            "edge_detected": edge_detected,
            "bet_receipt": bet_receipt.model_dump() if bet_receipt else None,
        })

    forecast.market = snapshot
    forecast.spread = spread
    forecast.edge_detected = edge_detected
    forecast.bet_receipt = bet_receipt
    return forecast


async def run_pipeline(req: ForecastRequest) -> ForecastResult:
    return await run_forecast_pipeline(req)


@app.get("/")
async def index():
    return FileResponse("frontend/index.html")


@app.get("/matches")
async def matches():
    """Return all WC 2026 groups with teams and matches — used by the bracket UI."""
    return await asyncio.to_thread(get_groups_data)


@app.get("/health")
async def health():
    return {"status": "ok", "weave_project": settings.weave_project_path}


@app.post("/forecast", response_model=ForecastResult)
async def forecast(req: ForecastRequest):
    return await run_pipeline(req)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
