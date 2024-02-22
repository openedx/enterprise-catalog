"""
Definitions of Celery tasks for the ai_curation app.
"""
import uuid

from celery import shared_task
from celery_utils.logged_task import LoggedTask

from enterprise_catalog.apps.ai_curation.enums import AICurationStatus
from enterprise_catalog.apps.ai_curation.models import AICurationTask


def _before_start(self, task_id, *args, **kwargs):  # pylint: disable=unused-argument
    """
    Mark the task as started.
    """
    AICurationTask.objects.update_or_create(
        task_id=task_id,
        defaults={
            'status': AICurationStatus.IN_PROGRESS,
            'payload': {'args': args, 'kwargs': kwargs},
        }
    )


def _on_failure(self, exc, task_id, *args, **kwargs):  # pylint: disable=unused-argument
    """
    Mark the task as started.
    """
    AICurationTask.objects.update_or_create(
        task_id=task_id,
        defaults={'status': AICurationStatus.FAILED},
        result={'exc': str(exc)},
    )


def _on_success(self, retval, task_id, *args, **kwargs):  # pylint: disable=unused-argument
    """
    Mark the task as started.
    """
    AICurationTask.objects.update_or_create(
        task_id=task_id,
        defaults={
            'status': AICurationStatus.COMPLETED,
            'result': retval,
        },
    )


def _after_return(self, *args, **kwargs):  # pylint: disable=unused-argument
    """
    Remove the old entries from AICurationTask.
    """
    AICurationTask.clear_outdated_entries()


@shared_task(
    base=LoggedTask,
    before_start=_before_start,
    on_failure=_on_failure,
    on_success=_on_success,
    after_return=_after_return,
    bind=True,
)
def trigger_ai_curations(self, query: str, catalog_id: uuid.UUID):  # pylint: disable=unused-argument
    """
    Triggers the AI curation process.
    """
    # TODO: Implement the AI curation process here and return the response.
    # TODO: Replace return value with correct data.
    return {'query': query, 'catalog_id': catalog_id}
