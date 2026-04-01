import os

from .bot import build_client
from .logging_config import setup_logging


def run() -> None:
    setup_logging()

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN environment variable")

    client = build_client()
    client.run(token)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
