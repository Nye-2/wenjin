"""Celery worker configuration and entry point."""

import logging
import sys

from src.task.celery_app import celery_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def start_worker(concurrency: int = 4, loglevel: str = "info", queues: list[str] | None = None):
    """Start a Celery worker.

    Args:
        concurrency: Number of worker processes/threads
        loglevel: Logging level (debug, info, warning, error)
        queues: List of queues to consume (default: all queues)
    """
    logger.info(f"Starting Celery worker with concurrency={concurrency}, loglevel={loglevel}")

    argv = [
        "worker",
        f"--concurrency={concurrency}",
        f"--loglevel={loglevel}",
        "--without-gossip",
        "--without-mingle",
    ]

    if queues:
        argv.extend(["-Q", ",".join(queues)])

    celery_app.worker_main(argv=argv)


def start_flower(port: int = 5555):
    """Start Flower (Celery monitoring UI).

    Args:
        port: Port to run Flower on
    """
    import subprocess

    logger.info(f"Starting Flower on port {port}")
    subprocess.run(["celery", "-A", "src.task.celery_app", "flower", f"--port={port}"])


if __name__ == "__main__":
    # Default worker startup
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    start_worker(concurrency=concurrency)
