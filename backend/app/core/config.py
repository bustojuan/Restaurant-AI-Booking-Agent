from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    host: str = "127.0.0.1"
    port: int = Field(default=8001, ge=1, le=65535)
    database_url: str = "sqlite:///./booking.db"
    local_api_token: SecretStr = Field(min_length=24)
    cors_origins: list[str] = ["http://localhost:5173"]
    seed_mock_data: bool = True
    image_catalog_path: str | None = None
    call_delay_seconds: float = Field(default=0.1, ge=0, le=30)
    call_timeout_seconds: float = Field(default=5, gt=0, le=60)
    ai_extraction_mode: Literal["deterministic", "responses"] = "deterministic"
    reasoning_model: str = "gpt-6-luna"
    voice_model: str = "gpt-live-1"
    voice_name: str = "marin"
    openai_api_key: SecretStr | None = None
    ai_max_steps: int = Field(default=1000, ge=20, le=5000)
    ai_retention_days: int = Field(default=30, ge=1, le=365)
    voice_sandbox_enabled: bool = False
    voice_max_seconds: int = Field(default=180, ge=10, le=600)
    approval_wait_seconds: int = Field(default=30, ge=5, le=120)
    real_telephony_enabled: bool = False
    twilio_account_sid: str | None = None
    twilio_auth_token: SecretStr | None = None
    twilio_phone_number: str | None = None
    telephony_public_origin: str | None = None
    telephony_gateway_port: int = Field(default=8002, ge=1, le=65535)
    telephony_allowed_numbers: list[str] = []
    telephony_start_hour: int = Field(default=10, ge=0, le=23)
    telephony_end_hour: int = Field(default=20, ge=1, le=24)
    # Set conservative provider tariffs before real calls; never infer prices.
    telephony_cost_per_minute: float | None = Field(default=None, gt=0)
    live_cost_per_minute: float | None = Field(default=None, gt=0)
    reasoning_reserved_cost_per_call: float | None = Field(default=None, gt=0)
    langsmith_tracing_enabled: bool = False
    voice_max_delegations: int = Field(default=8, ge=1, le=20)
    admin_api_token: SecretStr | None = Field(default=None, min_length=24)


@lru_cache
def get_settings() -> Settings:
    return Settings()
