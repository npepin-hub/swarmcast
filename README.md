# SwarmCast

**A self-improving multi-agent swarm for World Cup 2026 match forecasting — with Polymarket edge detection.**

> Feed it a match. A swarm of specialist agents deliberates in isolation. A critic finds what the collective is blind to. The swarm evolves and votes again. Consensus emerges. Then — and only then — it looks at Polymarket.

![SwarmCast demo](swarmcast-demo.gif)

---

## What it does

You pick a question ("Who wins?", "Predict the final score", "Over 2.5 goals?") and a match from the WC 2026 bracket. SwarmCast:

1. **Spawns N specialist agents** — the meta-orchestrator reads the question and decides which experts it needs (tacticians, historians, fitness analysts, set piece specialists, a psychological profiler, and always a contrarian biased against the favourite).
2. **Agents deliberate in parallel** — each runs a ReAct loop with live MCP tools, forming an independent opinion. They never see each other's reasoning. They never see Polymarket.
3. **A holistic critic audits the panel** — not to challenge individual agents, but to find what the *collective* is blind to. It returns coverage gaps, groupthink signals, and recommended actions. The orchestrator then spawns new agents, rewrites weak prompts, broadcasts gap signals.
4. **N revision rounds** (default: 5) — the evolved swarm revises its estimates. Each agent's vote trajectory is tracked across all rounds.
5. **Consensus** — confidence-weighted probability, predicted score, 80% CI, minority dissent.
6. **Polymarket comparison** — the market price is revealed for the first time. The spread is computed. If it exceeds the threshold, an edge is flagged.
7. **Every call traced in W&B Weave** — resolved matches become labeled training samples for v2 fine-tuning on CoreWeave.

---

## Sequence

```
User: Who wins? + Mexico vs South Africa
          │
          ▼
  ┌─────────────────────────────────────────────────────┐
  │  Meta-Orchestrator                                   │
  │  Spawns N specialists + guarantees a contrarian      │
  └────────────────────┬────────────────────────────────┘
                       │  parallel (asyncio.gather)
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    tactical      historical    contrarian   ... N agents
    analyst       stats         (always
    [MCP tools]   [MCP tools]    included)
          │            │            │
          └────────────┴────────────┘
                       │  round 1 votes
                       ▼
          ┌────────────────────────┐
          │  Holistic Critic       │
          │  Reads full panel      │
          │  Finds blind spots     │
          │  Recommends: spawn /   │
          │  rewrite / broadcast   │
          └────────────┬───────────┘
                       │  orchestrator acts
                       ▼
          ┌────────────────────────┐
          │  Revision Rounds 2..N  │  (LangGraph Swarm)
          │  Each agent sees only  │
          │  aggregate P — not     │
          │  each other's reasoning│
          └────────────┬───────────┘
                       │  final votes
                       ▼
          ┌────────────────────────┐
          │  Consensus             │
          │  Score · P · CI        │
          │  Minority dissent      │
          └────────────┬───────────┘
                       │  first contact with market
                       ▼
          ┌────────────────────────┐
          │  Polymarket            │
          │  Match market or       │
          │  winner-odds H2H       │
          │  Edge = |SwarmCast     │
          │         − Market|      │
          └────────────────────────┘
```

---

## The adversarial layer

Two mechanisms prevent the swarm from collapsing into groupthink:

**The Contrarian** is the only agent guaranteed to always be in the pool — `ensure_contrarian()` is called after spawning and after every critic action. It has the widest tool access of any specialist and is structurally biased against the favourite. It is the primary source of minority dissent.

**The Holistic Critic** does not challenge individual agents. It reads the full panel as one document and asks: *what is this collective blind to about this specific match?* Its output drives structural changes to the swarm before the revision rounds begin.

---

## Stack

| Component | Choice |
|---|---|
| LLM inference | W&B Inference (CoreWeave GPU) — `OpenPipe/Qwen3-14B-Instruct` |
| Agent orchestration | `asyncio.gather` (round 1) + LangGraph Swarm (revision rounds) |
| Live data | `wc26-mcp` + `@zafronix/wc-mcp` via MCP (LangChain tools) |
| Observability | W&B Weave — `@weave.op()` on every agent function |
| Backend | FastAPI + WebSockets |
| Visualization | p5.js Boids — 25 fish per specialist school |
| Polymarket | Gamma API (read) + winner-odds H2H fallback |

---

## Setup

```bash
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set in `.env`:

```env
WANDB_API_KEY=...       # required — W&B Inference + Weave tracing
WANDB_ENTITY=ceatp-ceatp
WANDB_PROJECT=swarmcast
WC_API_KEY=...          # required for @zafronix/wc-mcp (WC history 1930–2026)
                        # without it, agents lose H2H records, past rosters, standings
```

Node.js required for MCP servers (`npx` auto-installs on first run).

## Run

```bash
uvicorn backend.main:app --reload --port 8000
```

Open `http://localhost:8000` — pick a question, pick a match, watch the fish.

---

## Weave tracing

Every agent call is traced at `https://wandb.ai/{WANDB_ENTITY}/{WANDB_PROJECT}/weave`. When matches resolve, traces are labeled with the ground truth outcome — building the dataset for v2 fine-tuning on CoreWeave.

## Backtest

```bash
# /history page — runs SwarmCast against 2022 WC matches with known outcomes
open http://localhost:8000/history
```

---

## Endpoints

All routes require `WANDB_API_KEY` (Weave init at startup) and `WC_API_KEY` (historical MCP data).

| Path | Also requires | What it does |
|------|--------------|-------------|
| `GET /` | Node.js (npx) | Frontend — bracket loads from `wc26-mcp` |
| `GET /history` | — | 2022 WC backtest UI — serves from disk cache |
| `GET /health` | — | Health check |

## Project structure

```
backend/
  agents/      orchestrator, specialists, critic, delphi,
               swarm_langgraph, inference, pipeline
  data/        wc26.py (MCP client + disk cache)
  market/      gamma.py, edge.py
  eval/        wc_backtest.py, weave_eval.py, router.py
  main.py      all routes
frontend/
  index.html   bracket + question picker + consensus tile
  sketch.js    p5.js Boids
  ws.js        WebSocket client
  history.html backtest results page
requirements/
  SwarmCast.md full system brief
```

---

*Multi-Agent Orchestration Hackathon · MIT / The Engine · Boston Tech Week · June 2026*
