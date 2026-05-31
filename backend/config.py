from __future__ import annotations

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    wandb_api_key: str
    wandb_entity: str = "ceatp-ceatp"
    wandb_project: str = "swarmcast"

    wandb_inference_base_url: str = "https://api.inference.wandb.ai/v1"
    wandb_orchestrator_model: str = Field(
        default="OpenPipe/Qwen3-14B-Instruct",
        validation_alias=AliasChoices(
            "wandb_orchestrator_model",
            "WANDB_ORCHESTRATOR_MODEL",
            "WANDB_SPAWN_MODEL",
        ),
    )
    wandb_specialist_model: str = Field(
        default="OpenPipe/Qwen3-14B-Instruct",
        validation_alias=AliasChoices(
            "wandb_specialist_model",
            "WANDB_SPECIALIST_MODEL",
            "WANDB_VOTER_MODEL",
        ),
    )
    wandb_critic_model: str = "OpenPipe/Qwen3-14B-Instruct"
    wandb_delphi_model: str = "OpenPipe/Qwen3-14B-Instruct"
    use_langgraph_delphi: bool = True

    wc_api_key: str = ""
    football_data_api_key: str = ""
    api_football_key: str = ""

    polymarket_api_key: str = ""
    polymarket_private_key: str = ""
    polymarket_chain_id: int = 137
    edge_threshold: float = 0.08

    host: str = "0.0.0.0"
    port: int = 8000

    @computed_field
    @property
    def weave_project_path(self) -> str:
        return f"{self.wandb_entity}/{self.wandb_project}"


settings = Settings()
