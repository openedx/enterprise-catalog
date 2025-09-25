"""
Defines the Celery application for the enterprise_catalog project.
"""
import logging
from pathlib import Path

from celery import Celery
from celery.signals import heartbeat_sent, worker_ready, worker_shutdown


HEARTBEAT_FILE = Path("/tmp/worker_heartbeat")
READINESS_FILE = Path("/tmp/worker_ready")

logger = logging.getLogger(__name__)


@worker_ready.connect
def worker_ready(**_):
    logger.info('worker_ready signal received, touching the readiness file')
    READINESS_FILE.touch()


@worker_shutdown.connect
def worker_shutdown(**_):
    logger.info('worker_shutdown signal received, unlinking readiness and heartbeat files')
    READINESS_FILE.unlink(missing_ok=True)
    HEARTBEAT_FILE.unlink(missing_ok=True)


@heartbeat_sent.connect
def heartbeat(**_):
    HEARTBEAT_FILE.touch()


app = Celery('enterprise_catalog', )

# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


if __name__ == '__main__':
    app.start()
