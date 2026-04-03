"""Configuration management using Pydantic Settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    Attributes:
        discord_bot_token: Discord bot token (required)
        emoji_agent_manifest: Path to agent manifest file
        log_level: Application log level
        discord_log_level: Discord.py library log level
        anthropic_api_key: Anthropic API key (required)
        anthropic_base_url: Custom base URL for Claude API (optional)
    """

    # Discord Configuration
    discord_bot_token: str
    emoji_agent_manifest: str = "claude/agents/agents.yaml"

    # Logging Configuration
    log_level: str = "INFO"
    discord_log_level: str | None = None

    # Claude Code SDK Configuration
    anthropic_api_key: str

    # Optional: Custom base URL for Claude API (for proxy or alternative endpoints)
    anthropic_base_url: str | None = None

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
