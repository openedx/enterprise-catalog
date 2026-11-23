import os

from enterprise_catalog.settings.base import *
import tempfile

LMS_BASE_URL = 'https://edx.test.lms'
DISCOVERY_SERVICE_API_URL = 'https://edx.test.discovery/'
DISCOVERY_SERVICE_URL = 'https://edx.test.discovery/'
ENTERPRISE_LEARNER_PORTAL_BASE_URL = 'https://edx.test.learnerportal'
ECOMMERCE_BASE_URL = 'https://edx.test.ecommerce/'
LICENSE_MANAGER_BASE_URL = 'https://edx.test.licensemanager/'
STUDIO_BASE_URL = 'https://edx.test.cms'

# Use in-memory SQLite by default; migration CI supplies MySQL settings.
DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.environ.get('DB_NAME', ':memory:'),
        'USER': os.environ.get('DB_USER', ''),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', ''),
        'PORT': os.environ.get('DB_PORT', ''),
    },
}

# CELERY
CELERY_TASK_ALWAYS_EAGER = True
# END CELERY

results_dir = tempfile.TemporaryDirectory()
CELERY_RESULT_BACKEND = f'file://{results_dir.name}'
