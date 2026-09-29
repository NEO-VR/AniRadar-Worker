from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class AnimeChannel(BaseModel):
    """Single channel configuration for an anime."""
    channel_name: str = Field(..., min_length=1)

    @field_validator("channel_name")
    @classmethod
    def strip_channel(cls, v: str) -> str:
        return v.strip()


class AnimeConfig(BaseModel):
    """Anime configuration from JSON."""
    title: str = Field(..., min_length=1, description="Anime title")
    aliases: List[str] = Field(..., min_length=1, description="Alternative names for matching")
    channels: List[str] = Field(..., min_length=1, description="Source channels to monitor (recent scan)")
    searchable_channels: List[str] = Field(default_factory=list, description="Additional channels for full-history search")
    status: str = Field(default="RELEASING", description="RELEASING or FINISHED")
    total_episodes: Optional[int] = Field(default=None, description="Total episodes if known")
    genres: List[str] = Field(default_factory=list, description="Genre tags")
    poster_url: Optional[str] = Field(default=None, description="Poster image URL")

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Title cannot be empty or whitespace only")
        return stripped

    @field_validator("aliases", "channels", "searchable_channels", "genres", mode="before")
    @classmethod
    def validate_list_items(cls, v):
        if isinstance(v, list):
            return [item.strip() for item in v if isinstance(item, str) and item.strip()]
        return v

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, v):
        if not v:
            raise ValueError("At least one alias is required")
        return v

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, v):
        if not v:
            raise ValueError("At least one channel is required")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in ("RELEASING", "FINISHED"):
            return "RELEASING"
        return v


class AnimesConfig(BaseModel):
    """Root configuration object."""
    animes: List[AnimeConfig] = Field(default_factory=list)


def load_animes_config(file_path: str) -> AnimesConfig:
    """
    Loads and validates the anime configuration file using Pydantic.
    If the file does not exist, it creates a default empty one.
    """
    import json
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        # Initialize an empty list of animes
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"animes": []}, f, indent=2, ensure_ascii=False)
        return AnimesConfig(animes=[])

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from config file: {e}")

    # Validate with Pydantic - will raise ValidationError with detailed errors
    return AnimesConfig.model_validate(data)


def get_anime_dicts(config: AnimesConfig) -> List[dict]:
    """Convert Pydantic models to plain dicts for database operations."""
    return [anime.model_dump() for anime in config.animes]