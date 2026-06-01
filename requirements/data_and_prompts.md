# Data & Prompts — Quick Reference

---

## MCP Servers

### wc26-mcp — WC 2026 live data

> `get_odds` is **excluded** from all specialist tools — it contains betting odds and would violate the market blindness constraint.

| Tool | Params | Returns | Used by agents |
|------|--------|---------|---------------|
| `get_team_profile` | `team` | Coach, style, key players, rankings | statsbomb, wc26, contrarian |
| `compare_teams` | `team_a, team_b` | Side-by-side rankings, style | statsbomb, wc26, contrarian |
| `get_historical_matchups` | `team_a, team_b` | All WC meetings, aggregate record | statsbomb, kaggle_history, wc26, contrarian |
| `get_matches` | `team, date, group, round, status` | Fixtures | live_form, wc26, contrarian |
| `get_injuries` | `team, status` | Star player availability | live_injuries, wc26 |
| `get_news` | `team, category, limit` | ESPN / BBC / Reddit | live_form, live_injuries, wc26, contrarian |
| `get_standings` | `group` | Group power rankings | live_standings, wc26 |
| `get_groups` | `group` | Group composition, venues, schedule | live_standings |
| `get_bracket` | `round` | Full knockout bracket | live_standings |
| `what_to_know_now` | _(none)_ | Temporal briefing — what matters right now | live_form, wc26, contrarian |
| `get_venues` | `country, city` | Host venues | UI only |
| `get_schedule` | `date_from, date_to` | Full tournament schedule | UI only |
| `get_odds` | `category, group` | Winner odds, Golden Boot | **EXCLUDED from agents** |

### @zafronix/wc-mcp — WC history 1930–2026

| Tool | Params | Returns | Used by agents |
|------|--------|---------|---------------|
| `get_team` | `name` | Every WC appearance, positions, goals, win rates | statsbomb, kaggle_history, wc26, contrarian |
| `get_team_roster` | `name, year` | Full squad for a team + year | kaggle_history |
| `list_matches` | `year, stage, date` | All matches filterable | kaggle_history |
| `get_match` | `id` | Single match details | backtest eval |
| `get_standings` | `year, group` | Group standings with FIFA tiebreakers | backtest eval |
| `get_bracket` | `year` | Full knockout bracket for any tournament | backtest eval |
| `search_players` | `q, limit` | Player lookup | backtest eval |
| `get_player_career` | `name` | Full WC career | backtest eval |
| `list_tournaments` | _(none)_ | All 23 tournaments summary | backtest eval |
| `get_tournament` | `year` | Full details for one year | backtest eval |
| `get_trivia` | `year` | Record-setting moments, oddities | backtest eval |

---

## data_slice_id → MCP tools mapping

Specialists are assigned a `data_slice_id` by the orchestrator. At agent spawn time, `mcp_registry.py` translates this to a scoped list of LangChain tools. Agents call tools actively (ReAct loop) — they are **not** pre-injected with context dumps.

Defined in `backend/data/mcp_registry.py`:

| data_slice_id | Tools available |
|---|---|
| `statsbomb` | `wc26_get_team_profile`, `wc26_compare_teams`, `wc26_get_historical_matchups`, `history_get_team` |
| `kaggle_history` | `wc26_get_historical_matchups`, `history_get_team`, `history_get_team_roster`, `history_list_matches` |
| `live_form` | `wc26_get_matches`, `wc26_get_news`, `wc26_what_to_know_now` |
| `live_injuries` | `wc26_get_injuries`, `wc26_get_news` |
| `live_standings` | `wc26_get_standings`, `wc26_get_groups`, `wc26_get_bracket` |
| `contrarian` | All profile + form + history tools — widest view to find the underdog case |
| `wc26` | Full set — assigned when orchestrator doesn't specify a narrower slice |
| _(unknown)_ | Falls back to DEFAULT_TOOL_NAMES (same as `wc26`) |

---

## Prompts

| Prompt | File | What it does |
|--------|------|--------------|
| `_SPAWN_SYSTEM` | `backend/agents/orchestrator.py` | Tells Qwen3 to write N specialist definitions as a JSON array (role, focus, system_prompt, data_slice_id). Aims for 7–9 agents. |
| Specialist system prompts | Generated at runtime by `spawn_specialists()` | Written per match by the orchestrator — not hardcoded. Each includes independence instruction and market blindness rule. |
| `CRITIC_SYSTEM` | `backend/agents/critic.py` | Instructs Qwen3 to audit the full panel as one document — return coverage_gaps, groupthink_signals, recommended_actions (spawn / rewrite / broadcast). Never addresses individual agents. |
| Revision round addendum | `backend/agents/delphi.py` | Injected before each revision round 2..N — aggregate P + CI only, no reasoning chains. "Revise only if your data warrants it." |
| Verdict synthesis | `backend/agents/delphi.py:synthesize_verdict()` | Post-consensus narrative: Qwen3 writes a plain-English explanation of what drove the consensus and what the key dissent was. |

### Prompt flow

```
match_query + team_a + team_b
    │
    ▼
orchestrator (_SPAWN_SYSTEM)
    │  writes N specialist definitions (role, focus, system_prompt, data_slice_id)
    │  ensure_contrarian() guarantees one dissenter
    ▼
specialists run in parallel (round 1, full isolation)
    │  each runs a ReAct loop: calls MCP tools, reasons, emits structured vote
    │  output: { team_a_goals, team_b_goals, probability, confidence, key_signal, reasoning }
    ▼
critic (CRITIC_SYSTEM)
    │  reads full panel, returns gaps / groupthink / actions
    ▼
orchestrator acts (spawn / rewrite / broadcast)
    │  ensure_contrarian() called again
    ▼
revision rounds 2..N  [configurable, default N=5]
    │  each round: specialists see aggregate P + CI only (no reasoning chains)
    │  agents call MCP tools again if needed, revise vote
    │  all votes tracked: round_votes[round][agent]
    ▼
consensus
    │  confidence-weighted P + score + CI + minority dissent
    ▼
synthesize_verdict()
    │  plain-English narrative of what drove the answer
    ▼
output
```

---

## Caching

MCP subprocess calls are cached at two levels:

| Level | Location | TTL | Notes |
|---|---|---|---|
| In-process | `_cache` dict in `wc26.py` | 1 hour | Fast, lost on restart |
| Disk | `backend/data/` JSON files | Persistent | Survives restarts; written by `c495900` |

The backtest eval (`backend/eval/wc_backtest.py`) uses its own disk cache at `backend/eval/wc2022_match_cache.json`.
