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
