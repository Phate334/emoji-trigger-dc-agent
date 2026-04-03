import logging

from .config import Settings


def setup_logging(settings: Settings | None = None) -> None:
    """Configure logging for the application.

    Args:
        settings: Settings instance. If None, creates a new instance.
    """
    if settings is None:
        settings = Settings()

    log_level_name = settings.log_level.upper()
    discord_log_level_name = settings.get_discord_log_level().upper()

    log_level = getattr(logging, log_level_name, logging.INFO)
    discord_log_level = getattr(logging, discord_log_level_name, log_level)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )
    logging.getLogger("discord").setLevel(discord_log_level)
