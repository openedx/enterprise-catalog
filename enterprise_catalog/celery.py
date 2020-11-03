"""
Defines the Celery application for the enterprise_catalog project
"""
from celery import Celery


app = Celery('enterprise_catalog', )

# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.conf.task_protocol = 1
app.config_from_object('django.conf:settings', namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


if __name__ == '__main__':
    app.start()
