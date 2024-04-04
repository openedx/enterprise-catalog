"""
Definitions of Celery tasks for the ai_curation app.
"""
from celery import shared_task
from celery_utils.logged_task import LoggedTask

from enterprise_catalog.apps.ai_curation.utils import generate_curation


@shared_task(
    base=LoggedTask,
    bind=True,
)
def trigger_ai_curations(self, query: str, catalog_name: str):
    """
    Triggers the AI curation process.
    """
    return generate_curation(query, catalog_name, task_id=self.request.id)
