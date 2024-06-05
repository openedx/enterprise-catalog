"""
Definitions of Celery tasks for the ai_curation app.
"""
from celery import shared_task
from celery_utils.logged_task import LoggedTask

from enterprise_catalog.apps.ai_curation.utils import (
    generate_curation,
    track_ai_curation,
)
from enterprise_catalog.apps.api.v1.constants import SegmentEvents


@shared_task(
    base=LoggedTask,
    bind=True,
)
def trigger_ai_curations(self, query: str, catalog_name: str):
    """
    Triggers the AI curation process.
    """
    result = generate_curation(query, catalog_name, task_id=self.request.id)
    task_id = str(self.request.id)
    track_ai_curation(
        task_id=task_id,
        event_name=SegmentEvents.AI_CURATIONS_TASK_COMPLETED,
        properties={
            'task_id': task_id,
            'query': query,
            'catalog_name': catalog_name,
        }
    )
    return result
