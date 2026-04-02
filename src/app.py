import os
from pathlib import Path

from .agent_manifest import load_agent_manifest
from .bot import build_client
from .executor import AgentExecutor
from .logging_config import setup_logging


def run() -> None:
    setup_logging()

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing DISCORD_BOT_TOKEN environment variable")

    manifest_path = Path(os.getenv("EMOJI_AGENT_MANIFEST", "codex/agents/agents.yaml"))
    manifest = load_agent_manifest(manifest_path)
    executor = AgentExecutor()
    client = build_client(manifest=manifest, executor=executor)
    client.run(token)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
