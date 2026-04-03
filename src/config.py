"""Configuration management using Pydantic Settings."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    Attributes:
        discord_bot_token: Discord bot token (required)
        emoji_agent_manifest: Path to agent manifest file
        log_level: Application log level
        discord_log_level: Discord.py library log level
        anthropic_api_key: Anthropic API key (required)
        claude_model: Default Claude model id for all routes (optional)
        anthropic_base_url: Custom base URL for Claude API (optional)
    """

    # Discord Configuration
    discord_bot_token: str
    emoji_agent_manifest: str = "agents/agents.yaml"

    # Logging Configuration
    log_level: str = "INFO"
    discord_log_level: str | None = None

    # Claude Code SDK Configuration
    anthropic_api_key: str
    claude_model: str | None = None

    # Optional: Custom base URL for Claude API (for proxy or alternative endpoints)
    anthropic_base_url: str | None = None

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_anthropic_api_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ANTHROPIC_API_KEY must not be empty")

        placeholder_values = {
            "your-anthropic-api-key-here",
            "sk-temp",
        }
        if normalized in placeholder_values:
            raise ValueError(
                "ANTHROPIC_API_KEY is a placeholder value; set a real Anthropic API key"
            )

        return normalized

    @field_validator("claude_model")
    @classmethod
    def normalize_claude_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def get_discord_log_level(self) -> str:
        """Get Discord log level, falling back to log_level if not set."""
        return self.discord_log_level or self.log_level

    def get_emoji_agent_manifest_path(self) -> Path:
        """Get emoji agent manifest as a Path object."""
        return Path(self.emoji_agent_manifest)
