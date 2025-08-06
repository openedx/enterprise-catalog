from os import environ
import django
import yaml

from enterprise_catalog.settings.base import *
from enterprise_catalog.settings.utils import get_env_setting, get_logger_config


DEBUG = False
TEMPLATE_DEBUG = DEBUG

# IMPORTANT: With this enabled, the server must always be behind a proxy that
# strips the header HTTP_X_FORWARDED_PROTO from client requests. Otherwise,
# a user can fool our server into thinking it was an https connection.
# See
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-proxy-ssl-header
# for other warnings.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

ALLOWED_HOSTS = ['*']

# Keep track of the names of settings that represent dicts. Instead of overriding the values in base.py,
# the values read from disk should UPDATE the pre-configured dicts.
DICT_UPDATE_KEYS = ('JWT_AUTH',)

# This may be overridden by the YAML in catalog_CFG,
# but it should be here as a default.
MEDIA_STORAGE_BACKEND = {}
FILE_STORAGE_BACKEND = {}

# Allow extra headers for your specicfic production environment.
# Set this variable in the config yaml, and the values will be appended to CORS_ALLOW_HEADERS.
CORS_ALLOW_HEADERS_EXTRA = ()

CONFIG_FILE = get_env_setting('ENTERPRISE_CATALOG_CFG')
with open(CONFIG_FILE, encoding='utf-8') as f:
    config_from_yaml = yaml.load(f, Loader=yaml.SafeLoader)

    # Remove the items that should be used to update dicts, and apply them separately rather
    # than pumping them into the local vars.
    dict_updates = {key: config_from_yaml.pop(key, None) for key in DICT_UPDATE_KEYS}

    for key, value in dict_updates.items():
        if value:
            vars()[key].update(value)

    vars().update(config_from_yaml)

    # Unpack the media and files storage backend settings for django storages.
    # These dicts are not Django settings themselves, but they contain a mapping
    # of Django settings.
    STORAGES = {
        # this becomes the new DEFAULT_FILE_STORAGE
        'default': MEDIA_STORAGE_BACKEND,
        # pick an alias for your “other files” bucket
        'files': FILE_STORAGE_BACKEND,
        # you still need staticfiles here too
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }

# Must be generated after loading config YAML because LOGGING_FORMAT_STRING might be overridden.
LOGGING = get_logger_config(format_string=LOGGING_FORMAT_STRING)

DB_OVERRIDES = dict(
    PASSWORD=environ.get('DB_MIGRATION_PASS', DATABASES['default']['PASSWORD']),
    ENGINE=environ.get('DB_MIGRATION_ENGINE', DATABASES['default']['ENGINE']),
    USER=environ.get('DB_MIGRATION_USER', DATABASES['default']['USER']),
    NAME=environ.get('DB_MIGRATION_NAME', DATABASES['default']['NAME']),
    HOST=environ.get('DB_MIGRATION_HOST', DATABASES['default']['HOST']),
    PORT=environ.get('DB_MIGRATION_PORT', DATABASES['default']['PORT']),
)

# BEGIN CELERY
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_BROKER_URL = "{}://{}:{}@{}/{}".format(
    CELERY_BROKER_TRANSPORT,
    CELERY_BROKER_USER,
    CELERY_BROKER_PASSWORD,
    CELERY_BROKER_HOSTNAME,
    CELERY_BROKER_VHOST
)
CELERY_RESULT_BACKEND = 'django-db'
# END CELERY

# BEGIN CORS
# Inject extra allowed headers specific to a production environment.
CORS_ALLOW_HEADERS = (
    *CORS_ALLOW_HEADERS,
    *CORS_ALLOW_HEADERS_EXTRA,
)
# END CORS

for override, value in DB_OVERRIDES.items():
    DATABASES['default'][override] = value
