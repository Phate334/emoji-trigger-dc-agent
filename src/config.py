"""Configuration management using Pydantic Settings."""

from pathlib import Path
from typing import Self
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    Attributes:
        discord_bot_token: Discord bot token (required)
        emoji_agent_manifest: Path to agent manifest file
        log_level: Application log level
        discord_log_level: Discord.py library log level
        anthropic_api_key: Anthropic API key (optional)
        anthropic_auth_token: Custom Authorization bearer token (optional)
        claude_model: Default Claude model id for all routes (optional)
        claude_max_turns: Maximum Claude turns per triggered task
        anthropic_base_url: Custom base URL for Claude API (optional)
    """

    # Discord Configuration
    discord_bot_token: str
    emoji_agent_manifest: str = "agents/agents.yaml"

    # Logging Configuration
    log_level: str = "INFO"
    discord_log_level: str | None = None

    # Claude Code SDK Configuration
    anthropic_api_key: str | None = None
    anthropic_auth_token: str | None = None
    claude_model: str | None = None
    claude_max_turns: int = 4

    # Optional: Custom base URL for Claude API (for proxy or alternative endpoints)
    anthropic_base_url: str | None = None

    @field_validator("anthropic_api_key", "anthropic_auth_token")
    @classmethod
    def normalize_auth_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("claude_model", "anthropic_base_url")
    @classmethod
    def normalize_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("claude_max_turns")
    @classmethod
    def validate_claude_max_turns(cls, value: int) -> int:
        if value < 1:
            raise ValueError("CLAUDE_MAX_TURNS must be at least 1")
        return value

    @model_validator(mode="after")
    def validate_anthropic_configuration(self) -> Self:
        if self.anthropic_api_key is None and self.anthropic_auth_token is None:
            raise ValueError("Set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN")

        placeholder_values = {"your-anthropic-api-key-here", "sk-temp"}
        if (
            self.anthropic_api_key in placeholder_values
            and self.uses_official_anthropic_api()
            and self.anthropic_auth_token is None
        ):
            raise ValueError(
                "ANTHROPIC_API_KEY is a placeholder value; set a real Anthropic API key "
                "or provide ANTHROPIC_AUTH_TOKEN"
            )
        return self

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

    def uses_official_anthropic_api(self) -> bool:
        """Return True when the configured endpoint points at Anthropic directly."""
        if self.anthropic_base_url is None:
            return True

        candidate = self.anthropic_base_url
        if "://" not in candidate:
            candidate = f"https://{candidate}"

        return urlparse(candidate).hostname == "api.anthropic.com"

    def build_claude_sdk_env(self) -> dict[str, str]:
        """Build the env passed to the Claude CLI subprocess."""
        env: dict[str, str] = {}
        if self.anthropic_api_key is not None:
            env["ANTHROPIC_API_KEY"] = self.anthropic_api_key
        if self.anthropic_auth_token is not None:
            env["ANTHROPIC_AUTH_TOKEN"] = self.anthropic_auth_token
        if self.anthropic_base_url is not None:
            env["ANTHROPIC_BASE_URL"] = self.anthropic_base_url
        return env
