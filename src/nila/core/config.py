from pathlib import Path
from typing import Literal

from platformdirs import user_data_path
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NILA_", env_file=".env", extra="ignore")

    data_dir: Path = Field(default_factory=lambda: user_data_path("NILA-AI", appauthor=False))
    port: int = Field(default=8765, ge=1024, le=65535)
    api_token: SecretStr | None = None
    llm_provider: Literal["demo", "openai"] = "demo"
    openai_model: str | None = None
    openai_api_key: SecretStr | None = None
    max_steps: int = Field(default=5, ge=1, le=10)
    max_context_chars: int = Field(default=16000, ge=10000, le=64000)
    max_output_tokens: int = Field(default=1200, ge=128, le=4096)
    llm_timeout_seconds: float = Field(default=30, ge=1, le=120)
    task_timeout_seconds: float = Field(default=60, ge=1, le=300)
    approval_ttl_seconds: int = Field(default=300, ge=10, le=3600)

    @model_validator(mode="after")
    def validate_credentials(self) -> "Settings":
        if self.api_token is not None and len(self.api_token.get_secret_value()) < 32:
            raise ValueError("NILA_API_TOKEN must contain at least 32 characters")
        if self.llm_provider == "openai" and not (self.openai_model or "").strip():
            raise ValueError("Set NILA_OPENAI_MODEL when using the openai provider")
        return self

    @property
    def api_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"
