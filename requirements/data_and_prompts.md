# Data & Prompts — Quick Reference

## MCP Servers

### wc26-mcp — WC 2026 live data

| Tool | Params | Returns |
|------|--------|---------|
| `get_team_profile` | `team` | Coach, style, key players, rankings, odds |
| `compare_teams` | `team_a, team_b` | Side-by-side rankings, odds, style |
| `get_historical_matchups` | `team_a, team_b` | All WC meetings, aggregate record |
| `get_matches` | `team, date, group, round, status` | Fixtures |
| `get_standings` | `group` | Group power rankings |
| `get_bracket` | `round` | Full knockout bracket |
| `get_injuries` | `team, status` | Star player availability |
| `get_news` | `team, category, limit` | ESPN / BBC / Reddit (daily refresh) |
| `get_odds` | `category, group` | Winner odds, Golden Boot, group predictions |
| `get_groups` | `group` | Group composition, venues, schedule |
| `get_venues` | `country, city` | Host venues USA/Mexico/Canada |
| `get_schedule` | `date_from, date_to` | Full tournament schedule |
| `what_to_know_now` | _(none)_ | Temporal briefing — what matters right now |

### @zafronix/wc-mcp — WC history 1930–2026

| Tool | Params | Returns |
|------|--------|---------|
| `get_team` | `name` | Every WC appearance, positions, goals, win rates |
| `get_team_roster` | `name, year` | Full squad for a team + year |
| `list_matches` | `year, stage, date` | All matches filterable |
| `get_match` | `id` | Single match details |
| `get_standings` | `year, group` | Group standings with FIFA tiebreakers |
| `get_bracket` | `year` | Full knockout bracket for any tournament |
| `search_players` | `q, limit` | Player lookup across all tournaments |
| `get_player_career` | `name` | Full WC career for any player |
| `list_tournaments` | _(none)_ | All 23 tournaments summary |
| `get_tournament` | `year` | Full details for one year |
| `get_trivia` | `year` | Record-setting moments, oddities |

---

## Context bundle → data_slice_id mapping

How `wc26.py` maps MCP calls to specialist slices:

| data_slice_id | MCP calls |
|---|---|
| `statsbomb` | `get_team_profile` × 2 + `compare_teams` |
| `kaggle_history` | `get_historical_matchups` + `get_team` × 2 (history MCP) |
| `live_form` | `get_matches` × 2 + `get_news` × 2 |
| `live_injuries` | `get_injuries` × 2 |
| `live_standings` | `get_standings` |

---

## Prompts

| Prompt | File | What it does |
|--------|------|--------------|
| `_SPAWN_SYSTEM` | `backend/agents/orchestrator.py:22` | Tells the orchestrator LLM to write specialist definitions as a JSON array |
| Specialist system prompts | generated at runtime by `spawn_specialists()` | Written by the orchestrator per match — not hardcoded |
| `CRITIC_SYSTEM` | `backend/agents/critic.py:11` | Instructs Haiku to audit the full panel as one doc, return coverage gaps + groupthink signals + actions |
| Delphi addendum | `backend/agents/delphi.py:~45` | Sparse signal injected into specialist prompts before round 2 — aggregate P + CI only, no reasoning chains |

### Prompt flow

```
match_query
    │
    ▼
orchestrator (_SPAWN_SYSTEM)
    │  writes specialist definitions (role + system_prompt + data_slice_id)
    ▼
specialists run in parallel
    │  each sees: system_prompt + MCP context for their data_slice_id
    ▼
critic (CRITIC_SYSTEM)
    │  reads full panel, returns gaps / groupthink / actions
    ▼
orchestrator acts (spawn / rewrite / broadcast)
    ▼
delphi round 2
    │  specialists get original prompt + delphi addendum (aggregate P only)
    ▼
consensus
```
