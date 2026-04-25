from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentLLMConfig(BaseModel):
    """Per-agent LLM dials. Tight temperature + small max_tokens keeps
    routing deterministic and reduces latency."""
    temperature: float = 1.0
    max_tokens: int = 12000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- ILMU / GLM-5.1 ----
    ilmu_api_key: str = "dev-key"
    ilmu_base_url: str = "https://api.ilmu.ai/v1"
    ilmu_model: str = "ilmu-glm-5.1"
    # Most OpenAI-compatible servers support JSON response_format; if the
    # deployment rejects it we fall back to schema-injection-only.
    ilmu_supports_json_mode: bool = True
    ilmu_timeout_seconds: float = 120.0
    ilmu_max_retries: int = 2

    # ---- LangSmith ----
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "Orion"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_dashboard_url: str = "https://smith.langchain.com"

    # ---- App ----
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    max_upload_bytes: int = 8 * 1024 * 1024  # 8 MB

    # ---- Policy thresholds (guidance, not hard branches) ----
    auto_approve_limit_myr: float = 500.0
    escalation_limit_myr: float = 5000.0

    # ---- Per-agent LLM config ----
    cfg_intake: AgentLLMConfig = AgentLLMConfig(temperature=0.1, max_tokens=1400)
    cfg_intelligence: AgentLLMConfig = AgentLLMConfig(temperature=0.2, max_tokens=2000)  # higher for tool-loop
    cfg_supervisor: AgentLLMConfig = AgentLLMConfig(temperature=0.0, max_tokens=800)    # deterministic routing
    cfg_policy: AgentLLMConfig = AgentLLMConfig(temperature=0.0, max_tokens=1600)
    cfg_validation: AgentLLMConfig = AgentLLMConfig(temperature=0.1, max_tokens=900)
    cfg_approval: AgentLLMConfig = AgentLLMConfig(temperature=0.0, max_tokens=800)

    # ---- Intelligence tool-loop cap ----
    intelligence_max_iterations: int = 5

    # ---- Fuzzy match tuning (P2.2) ----
    fuzzy_match_threshold: float = 55.0    # min rapidfuzz partial_ratio score to include a match
    fuzzy_top_k: int = 10                  # max candidates passed into fuzzy scorer
    fuzzy_debug_logging: bool = False      # print match scores to stdout for tuning

    # ---- Paths ----
    project_root: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = Path(__file__).resolve().parent.parent / "data"


settings = Settings()


def langsmith_is_live() -> bool:
    return bool(
        settings.langsmith_tracing
        and settings.langsmith_api_key
        and settings.langsmith_api_key not in ("replace-me", "")
    )


def wire_langsmith() -> None:
    """Export LangSmith env vars so langsmith SDK + LangGraph pick them
    up automatically. Safe to call multiple times."""
    import os

    if langsmith_is_live():
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
    else:
        # Explicitly disable so the SDK doesn't attempt to send traces
        # even if stale env vars are present from a previous session.
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
