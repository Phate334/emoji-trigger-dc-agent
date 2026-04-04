import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

from .agent_manifest import load_agent_manifest
from .bot import build_client
from .config import Settings
from .executor import AgentExecutor
from .logging_config import setup_logging

logger = logging.getLogger("emoji-trigger-agent")


def run() -> None:
    settings = Settings()
    setup_logging(settings)

    logger.info("Starting emoji trigger agent")
    logger.debug("Using manifest: %s", settings.emoji_agent_manifest)

    outputs_root = settings.get_agent_outputs_root_path()
    _ensure_writable_directory(outputs_root)

    manifest = load_agent_manifest(settings.get_emoji_agent_manifest_path())
    executor = AgentExecutor(
        default_model_id=settings.claude_model,
        max_turns=settings.claude_max_turns,
        outputs_root=outputs_root,
        sdk_env=settings.build_claude_sdk_env(),
    )
    client = build_client(manifest=manifest, executor=executor)
    client.run(settings.discord_bot_token)


def main() -> None:
    run()


def _ensure_writable_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path, prefix=".write-check-", delete=True):
        pass


if __name__ == "__main__":
    main()
