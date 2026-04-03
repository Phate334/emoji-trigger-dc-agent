import logging
import os


def setup_logging() -> None:
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    discord_log_level_name = os.getenv("DISCORD_LOG_LEVEL", log_level_name).upper()

    log_level = getattr(logging, log_level_name, logging.INFO)
    discord_log_level = getattr(logging, discord_log_level_name, log_level)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )
    logging.getLogger("discord").setLevel(discord_log_level)
