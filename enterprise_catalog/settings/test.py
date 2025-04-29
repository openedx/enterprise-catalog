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

# IN-MEMORY TEST DATABASE
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    },
}
# END IN-MEMORY TEST DATABASE

# CELERY
CELERY_TASK_ALWAYS_EAGER = True
# END CELERY

results_dir = tempfile.TemporaryDirectory()
CELERY_RESULT_BACKEND = f'file://{results_dir.name}'

XPERT_AI_API_V2 = 'http://test.chat.ai'
XPERT_AI_CLIENT_ID = 'test client id'
XPERT_AICURATION_SYSTEM_MESSAGE = 'test system prompt'
CHAT_COMPLETION_API_CONNECT_TIMEOUT = 1
CHAT_COMPLETION_API_READ_TIMEOUT = 15
