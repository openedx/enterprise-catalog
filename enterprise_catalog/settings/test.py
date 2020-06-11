import os

from enterprise_catalog.settings.base import *

LMS_BASE_URL = 'https://edx.test.lms'
DISCOVERY_SERVICE_API_URL = 'https://edx.test.discovery/'

ENABLE_DJANGO_SILK = False

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
# END CELERY
