# SwarmCast

A self-improving multi-agent swarm for World Cup match forecasting, with optional Polymarket edge detection.

Specialists deliberate in parallel (W&B Inference), a holistic critic audits the panel, Delphi round 2 revises votes (LangGraph Swarm by default), and consensus is traced in **Weave** (`ceatp-ceatp/swarmcast` by default). Market validation runs only after the vote is sealed.

## Weave tracing

```text
https://wandb.ai/{WANDB_ENTITY}/{WANDB_PROJECT}/weave
```

- `run_forecast_pipeline` → `run_deliberation` (`swarm_run_id`)
  - `spawn_specialists` → `run_swarm` → `run_critic` → `act_on_critique` → `run_delphi_round` → `aggregate`
  - Delphi: `run_delphi_langgraph` or parallel W&B (`USE_LANGGRAPH_DELPHI=false`)
- `run_market_validation` (post-deliberation)

## Requirements

- Python 3.9+
- Node.js + `npx` (for MCP data servers)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set WANDB_API_KEY, WC_API_KEY as needed
```

## Environment

```env
WANDB_API_KEY=...
WANDB_ENTITY=ceatp-ceatp
WANDB_PROJECT=swarmcast
USE_LANGGRAPH_DELPHI=true
WC_API_KEY=...
POLYMARKET_PRIVATE_KEY=...   # optional — CLOB stubbed without py-clob-client
```

## Data sources

| MCP | Provides |
|-----|---------|
| `wc26-mcp` | WC 2026 fixtures, teams, form, injuries, standings, H2H |
| `@zafronix/wc-mcp` | Historical WC data 1930–2026 |

Both run via `npx` on first use.

## Run

```bash
uvicorn backend.main:app --reload --port 8000
```

Open http://localhost:8000

## Project structure

```
backend/
  agents/         pipeline, orchestrator, specialists, critic, delphi, swarm_langgraph, inference
  data/           wc26.py (MCP client)
  market/         gamma.py, edge.py (validation after vote)
  observability/  weave_tracer.py
  main.py         /forecast + /ws
frontend/         p5.js Boids visualization
```

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Frontend |
| `GET` | `/health` | Health check |
| `POST` | `/forecast` | Full swarm pipeline |
| `WS` | `/ws` | Real-time agent events |
