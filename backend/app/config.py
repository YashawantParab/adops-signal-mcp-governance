from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SignalOps AI"
    app_version: str = "1.0.0"
    environment: str = "local"
    database_url: str = "sqlite:///./adops_signal.db"
    frontend_origin: str = "http://localhost:3000"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-5.4-mini"
    openai_timeout_seconds: float = 25.0
    llm_enabled: bool = True
    rag_embedding_provider: str = "local"
    rag_embedding_model: str = "text-embedding-3-small"

    # Governed MCP agent (Phase 1) -------------------------------------------------
    llm_provider: str = "openai"  # "openai" | "anthropic" - selects the provider used by the governed MCP agent
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-5"
    anthropic_timeout_seconds: float = 25.0
    mcp_agent_enabled: bool = True
    # Empty by default so the MCP client falls back to sys.executable - the
    # exact interpreter/venv the backend itself is running under, guaranteeing
    # the mcp-server subprocess has every dependency the backend has. Only
    # override this if the MCP server must run under a different interpreter.
    mcp_server_command: str = ""
    mcp_server_args: str = "-m adops_signal_mcp.server"
    mcp_server_cwd: Optional[str] = None  # defaults to <repo_root>/mcp-server when unset
    max_agent_steps: int = 6
    max_agent_tool_calls: int = 6
    max_agent_tokens: int = 20000
    agent_timeout_seconds: float = 45.0
    max_run_cost_usd: Optional[float] = None
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    auth_enabled: bool = True
    demo_admin_email: str = "adops@demo.adops.local"
    demo_admin_password: str = "SignalDemo!2026"
    log_level: str = "INFO"
    agent_rate_limit_per_minute: int = 20
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://") and "+psycopg" not in value:
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def llm_available(self) -> bool:
        return bool(self.llm_enabled and self.openai_api_key)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def mcp_agent_llm_available(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
