"""W&B Inference client shared by all agents."""
from __future__ import annotations

import json
import re
from typing import Any

import weave
from openai import OpenAI

from ..config import settings

VOTE_JSON = """
Respond with ONLY valid JSON (no markdown):
{"team_a_goals": <int >= 0>, "team_b_goals": <int >= 0>, "probability": <float 0-1 P(team A wins)>, "confidence": <float 0-1>, "key_signal": "<one line>", "reasoning": "<=200 words>", "uncertainty_flag": <true|false>}
Team A goals = team_a_goals; team B goals = team_b_goals. Predict a realistic final score and a win probability consistent with that score.
"""


def parse_goals(data: dict) -> tuple[int, int]:
    """Extract predicted score from vote JSON (several key shapes)."""
    if "team_a_goals" in data and "team_b_goals" in data:
        return int(data["team_a_goals"]), int(data["team_b_goals"])
    nested = data.get("predicted_score")
    if isinstance(nested, dict):
        a = nested.get("team_a_goals", nested.get("team_a", 0))
        b = nested.get("team_b_goals", nested.get("team_b", 0))
        return int(a), int(b)
    raw = data.get("score")
    if isinstance(raw, str) and "-" in raw:
        left, _, right = raw.partition("-")
        try:
            return int(left.strip()), int(right.strip())
        except ValueError:
            pass
    return 0, 0


def extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def extract_json_array(text: str) -> list[Any] | None:
    if not text:
        return None
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    try:
        data = json.loads(text.strip())
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


@weave.op()
def inference_chat(system: str, user: str, model: str) -> str:
    client = OpenAI(
        base_url=settings.wandb_inference_base_url,
        api_key=settings.wandb_api_key,
        project=settings.weave_project_path,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""
