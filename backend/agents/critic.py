"""Holistic critic — W&B Inference."""
from __future__ import annotations

import weave

from ..config import settings
from ..schemas import AgentVote, CritiqueOutput, CriticAction, RecommendedAction
from .inference import extract_json_object, inference_chat

CRITIC_SYSTEM = """\
You are a system-level auditor for a multi-agent forecasting panel.
You receive the full panel output as a single unified document.

Rules:
- Do NOT comment on individual agents by name.
- Do NOT antagonize agents for the sake of debate.
- Identify what the COLLECTIVE analysis is missing about this SPECIFIC match.
- Return ONLY valid JSON:
  "coverage_gaps": list of strings,
  "groupthink_signals": list of strings,
  "recommended_actions": list of {"action": "spawn"|"rewrite"|"broadcast", "rationale": string, "target_role": string|null}
"""


def _format_panel(votes: list[AgentVote]) -> str:
    lines = []
    for v in votes:
        lines.append(
            f"P={v.probability:.2f} conf={v.confidence:.2f} flag={v.uncertainty_flag}\n"
            f"Signal: {v.key_signal}\nReasoning: {v.reasoning}\n"
        )
    return "\n---\n".join(lines)


@weave.op()
def run_critic(votes: list[AgentVote], match_query: str) -> CritiqueOutput:
    panel_doc = f"Match question: {match_query}\n\n" + _format_panel(votes)
    raw = inference_chat(CRITIC_SYSTEM, panel_doc, settings.wandb_critic_model)
    data = extract_json_object(raw) or {}
    actions = []
    for a in data.get("recommended_actions", []):
        try:
            actions.append(
                RecommendedAction(
                    action=CriticAction(a["action"]),
                    rationale=a.get("rationale", ""),
                    target_role=a.get("target_role"),
                )
            )
        except (KeyError, ValueError):
            continue
    if not actions and data.get("coverage_gaps"):
        actions.append(
            RecommendedAction(
                action=CriticAction.broadcast,
                rationale=" ".join(data["coverage_gaps"])[:500],
                target_role=None,
            )
        )
    return CritiqueOutput(
        coverage_gaps=data.get("coverage_gaps", []),
        groupthink_signals=data.get("groupthink_signals", []),
        recommended_actions=actions,
    )
