from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_core import ValidationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )

    # Telegram API
    API_ID: int = Field(..., description="Telegram API ID from my.telegram.org")
    API_HASH: str = Field(..., description="Telegram API Hash from my.telegram.org")
    SESSION_NAME: str = Field(default="anime_tracker", description="Telethon session file name")

    # Target group for posting
    MONITOR_GROUP: int = Field(..., description="Target group/forum name to monitor")

    # Check interval
    CHECK_INTERVAL: int = Field(default=600, ge=10, description="Check interval in seconds (min 10)")

    # Concurrency
    MAX_CONCURRENT_SCANS: int = Field(default=5, ge=1, le=20, description="Max concurrent channel scans")
    db_path: Path = Field(default=Path("/app/db/anime_tracker.db"), description="Path to SQLite database")
    session_path: Path = Field(default=Path("/app/sessions/anime_tracker"), description="Path to Telethon session file")

    @field_validator("API_ID")
    @classmethod
    def validate_api_id(cls, v):
        if not isinstance(v, int) or v <= 0:
            raise ValueError("API_ID must be a positive integer")
        return v

    @field_validator("API_HASH")
    @classmethod
    def validate_api_hash(cls, v):
        if not v or len(v.strip()) < 10:
            raise ValueError("API_HASH must be a valid non-empty string")
        return v.strip()


    @field_validator("SESSION_NAME")
    @classmethod
    def validate_session_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("SESSION_NAME cannot be empty")
        return v.strip()


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        try:
            _settings = Settings()
        except ValidationError as e:
            # Re-raise with clearer message for missing required fields
            errors = e.errors()
            for error in errors:
                if error["type"] == "missing" and error["loc"][0] in ("API_ID", "API_HASH"):
                    raise ValueError(f"{error['loc'][0]} is missing from .env or environment.") from e
            raise
    return _settings