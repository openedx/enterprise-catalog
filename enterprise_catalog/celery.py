"""
Defines the Celery application for the enterprise_catalog project
"""
from __future__ import absolute_import, unicode_literals

from celery import Celery
from django.conf import settings


app = Celery('enterprise_catalog', )

# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object(settings, namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


if __name__ == '__main__':
    app.start()
