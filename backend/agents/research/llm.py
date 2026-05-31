"""W&B Inference LLM for research LangGraph nodes."""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from ...config import settings


def chat_model(model: str | None = None) -> ChatOpenAI:
    model = model or settings.wandb_research_model
    return ChatOpenAI(
        model=model,
        api_key=settings.wandb_api_key,
        base_url=settings.wandb_inference_base_url,
        default_headers={"X-Wandb-Project": settings.weave_project_path},
        temperature=0.1,
    )
