"""ReAct-style loop using W&B chat model."""
from __future__ import annotations

import ast
import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from .llm import chat_model


def _generation_text(content: object) -> str:
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content or "")


def run_react_agent(
    system_instruction: str,
    tools_available: str = "None available. Rely on internal reasoning.",
    max_loops: int = 3,
    model: str | None = None,
) -> str:
    no_tools = (
        not tools_available
        or "none available" in tools_available.lower()
        or not tools_available.strip()
    )
    react_rules = """
CRITICAL RULES:
1. Use prefix 'Thought:' then either 'Final Answer:' or 'Action:'.
2. Prefer finishing in one turn with 'Final Answer:'.
3. Keep Thought to 1-2 sentences.
"""
    if no_tools:
        react_rules += "4. No tools — provide Final Answer immediately.\n"

    llm = chat_model(model)
    scratchpad = ""
    effective_max = 2 if no_tools else max_loops

    for loop_count in range(effective_max):
        user = f"""{system_instruction}

Available Tools:
{tools_available}
{react_rules}
{scratchpad}"""
        response = llm.invoke(
            [
                SystemMessage(content="You are a research agent for match forecasting."),
                HumanMessage(content=user),
            ]
        )
        generation = _generation_text(response.content)
        scratchpad += f"\n{generation}"

        final_match = re.search(
            r"Final\s*Answer\s*:\s*(.*)", generation, re.DOTALL | re.IGNORECASE
        )
        if final_match:
            return final_match.group(1).strip()

        if no_tools or loop_count == effective_max - 1:
            json_block = re.search(r"(\{.*\})", generation, re.DOTALL)
            if json_block:
                return json_block.group(1).strip()
            thought_match = re.search(
                r"Thought:\s*(.*)", generation, re.DOTALL | re.IGNORECASE
            )
            if thought_match:
                return thought_match.group(1).strip()
            return generation.strip()

        scratchpad += "\nObservation: Provide Final Answer in valid JSON if asked."

    return '{"error": "loop limit reached"}'


def extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    raw = match.group() if match else text.strip()
    json_block = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
    if json_block:
        raw = json_block.group(1).strip()
    elif raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n|```$", "", raw).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        try:
            data = ast.literal_eval(raw)
            return data if isinstance(data, dict) else None
        except (SyntaxError, ValueError):
            return None
