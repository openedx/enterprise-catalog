"""
Definitions of Celery tasks for the ai_curation app.
"""
import uuid

from celery import shared_task
from celery_utils.logged_task import LoggedTask


@shared_task(
    base=LoggedTask,
    bind=True,
)
def trigger_ai_curations(self, query: str, catalog_id: uuid.UUID):  # pylint: disable=unused-argument
    """
    Triggers the AI curation process.
    """
    # TODO: Implement the AI curation process here and return the response.
    # TODO: Replace return value with correct data.
    return {'query': query, 'catalog_id': str(catalog_id)}
