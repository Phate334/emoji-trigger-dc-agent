import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

from .agent_manifest import load_agent_manifest
from .bot import build_client
from .config import Settings
from .executor import AgentExecutor
from .logging_config import setup_logging
from .trigger_queue import TriggerQueueStore, TriggerQueueWorker

logger = logging.getLogger("emoji-trigger-agent")


def run() -> None:
    settings = Settings()  # type: ignore[call-arg]
    setup_logging(settings)

    logger.info("Starting emoji trigger agent")
    logger.debug("Using manifest: %s", settings.emoji_agent_manifest)

    outputs_root = settings.get_agent_outputs_root_path()
    _ensure_writable_directory(outputs_root)
    trigger_queue_db_path = settings.get_trigger_queue_db_path()
    trigger_queue_db_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = load_agent_manifest(settings.get_emoji_agent_manifest_path())
    queue_store = TriggerQueueStore(trigger_queue_db_path)
    queue_store.initialize()
    executor = AgentExecutor(
        default_model_id=settings.claude_model,
        max_turns=settings.claude_max_turns,
        outputs_root=outputs_root,
        sdk_env=settings.build_claude_sdk_env(),
    )
    trigger_worker = TriggerQueueWorker(
        store=queue_store,
        manifest=manifest,
        executor=executor,
        poll_interval_seconds=settings.trigger_queue_poll_interval_seconds,
        concurrency=settings.trigger_queue_worker_concurrency,
        claim_timeout_seconds=settings.trigger_queue_claim_timeout_seconds,
        retry_count=settings.trigger_queue_retry_count,
        retry_delay_seconds=settings.trigger_queue_retry_delay_seconds,
    )
    client = build_client(
        manifest=manifest,
        queue_store=queue_store,
        trigger_worker=trigger_worker,
    )
    client.run(settings.discord_bot_token)


def main() -> None:
    run()


def _ensure_writable_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path, prefix=".write-check-", delete=True):
        pass


if __name__ == "__main__":
    main()
