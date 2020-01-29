import os

from enterprise_catalog.settings.base import *

DISCOVERY_SERVICE_API_URL = 'https://edx.test.discovery/'

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
CELERY_ALWAYS_EAGER = True
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://:password@redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://:password@redis:6379/0')
CELERY_IGNORE_RESULT = True
# END CELERY
