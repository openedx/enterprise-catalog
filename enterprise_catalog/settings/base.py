import os
import platform
from logging.handlers import SysLogHandler
from os.path import abspath, dirname, join

from corsheaders.defaults import default_headers as corsheaders_default_headers

from enterprise_catalog.apps.catalog.constants import (
    DEFAULT_COURSE_FIELDS_TO_PLUCK_FROM_SEARCH_ALL,
    ENTERPRISE_CATALOG_ADMIN_ROLE,
    ENTERPRISE_CATALOG_LEARNER_ROLE,
    SYSTEM_ENTERPRISE_ADMIN_ROLE,
    SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE,
    SYSTEM_ENTERPRISE_LEARNER_ROLE,
    SYSTEM_ENTERPRISE_OPERATOR_ROLE,
)
from enterprise_catalog.settings.utils import get_env_setting, get_logger_config


# PATH vars
here = lambda *x: join(abspath(dirname(__file__)), *x)
PROJECT_ROOT = here("..")
root = lambda *x: join(abspath(PROJECT_ROOT), *x)


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('ENTERPRISE_CATALOG_SECRET_KEY', 'insecure-secret-key')

DEFAULT_HASHING_ALGORITHM = "sha1"

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = []

# Application definition

INSTALLED_APPS = (
    'clearcache',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles'
)

THIRD_PARTY_APPS = (
    # API Documentation
    'drf_yasg',
    'edx_api_doc_tools',

    'corsheaders',
    'csrf.apps.CsrfAppConfig',  # Enables frontend apps to retrieve CSRF tokens
    'django_celery_results',  # Enables a Django model as the celery result backend
    'djangoql',
    'rest_framework',
    'simple_history',
    'social_django',
    'waffle',
    'release_util',
    'rules.apps.AutodiscoverRulesConfig',
)

PROJECT_APPS = (
    'enterprise_catalog.apps.track',
    'enterprise_catalog.apps.core',
    'enterprise_catalog.apps.catalog',
    'enterprise_catalog.apps.curation',
    'enterprise_catalog.apps.api',
)

INSTALLED_APPS += THIRD_PARTY_APPS
INSTALLED_APPS += PROJECT_APPS

MIDDLEWARE = (
    'log_request_id.middleware.RequestIDMiddleware',
    'edx_django_utils.monitoring.CookieMonitoringMiddleware',
    'edx_django_utils.monitoring.DeploymentMonitoringMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'edx_rest_framework_extensions.auth.jwt.middleware.JwtAuthCookieMiddleware',
    'edx_rest_framework_extensions.auth.jwt.middleware.JwtRedirectToLoginIfUnauthenticatedMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'social_django.middleware.SocialAuthExceptionMiddleware',
    'crum.CurrentRequestUserMiddleware',
    'waffle.middleware.WaffleMiddleware',
    # Lets simple history track which user made changes via API.  Manual changes via django admin already have the user
    # tracked via SimpleHistoryAdmin.
    'simple_history.middleware.HistoryRequestMiddleware',
    'edx_django_utils.cache.middleware.RequestCacheMiddleware',
)

# https://github.com/dabapps/django-log-request-id
LOG_REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
GENERATE_REQUEST_ID_IF_NOT_IN_HEADER = False
REQUEST_ID_RESPONSE_HEADER = "X-Request-ID"
NO_REQUEST_ID = "None"
LOG_REQUESTS = False

# Enable CORS
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = corsheaders_default_headers + (
    'use-jwt-cookie',
)
CORS_ORIGIN_WHITELIST = []

ROOT_URLCONF = 'enterprise_catalog.urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'enterprise_catalog.wsgi.application'

# Database
# https://docs.djangoproject.com/en/1.11/ref/settings/#databases
# Set this value in the environment-specific files (e.g. local.py, production.py, test.py)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.',
        'NAME': 'enterprise_catalog',
        'USER': 'entcatalog001',
        'PASSWORD': 'password',
        'HOST': 'localhost',  # Empty for localhost through domain sockets or '127.0.0.1' for localhost through TCP.
        'PORT': '',  # Set to empty string for default.
        'ATOMIC_REQUESTS': False,
        # The default isolation level for MySQL is REPEATABLE READ, which is a little too aggressive
        # for our needs, particularly around reading celery task state via django-celery-results.
        # https://dev.mysql.com/doc/refman/8.0/en/innodb-transaction-isolation-levels.html#isolevel_read-committed
        'OPTIONS': {
            'isolation_level': 'read committed',
        },
    }
}

# Django Rest Framework
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.coreapi.AutoSchema',
    'PAGE_SIZE': 10,
    'TEST_REQUEST_DEFAULT_FORMAT': 'json',
}

# Internationalization
# https://docs.djangoproject.com/en/dev/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

LOCALE_PATHS = (
    root('conf', 'locale'),
)


# MEDIA CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = root('media')

# See: https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = '/media/'
# END MEDIA CONFIGURATION


# STATIC FILE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = root('assets')

# See: https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = '/static/'

# See: https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = (
    root('static'),
)

# TEMPLATE CONFIGURATION
# See: https://docs.djangoproject.com/en/1.11/ref/settings/#templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'DIRS': (
            root('templates'),
        ),
        'OPTIONS': {
            'context_processors': (
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.request',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                'enterprise_catalog.apps.core.context_processors.core',
            ),
            'debug': True,  # Django will only display debug pages if the global DEBUG setting is set to True.
        }
    },
]
# END TEMPLATE CONFIGURATION


# COOKIE CONFIGURATION
# The purpose of customizing the cookie names is to avoid conflicts when
# multiple Django services are running behind the same hostname.
# Detailed information at: https://docs.djangoproject.com/en/dev/ref/settings/
SESSION_COOKIE_NAME = 'catalog_sessionid'
CSRF_COOKIE_NAME = 'catalog_csrftoken'
LANGUAGE_COOKIE_NAME = 'openedx-language-preference'
# END COOKIE CONFIGURATION

CSRF_COOKIE_SECURE = False
CSRF_TRUSTED_ORIGINS = []

# AUTHENTICATION CONFIGURATION
LOGIN_URL = '/login/'
LOGOUT_URL = '/logout/'

AUTH_USER_MODEL = 'core.User'

AUTHENTICATION_BACKENDS = (
    'auth_backends.backends.EdXOAuth2',
    'rules.permissions.ObjectPermissionBackend',
    'django.contrib.auth.backends.ModelBackend',
)

ENABLE_AUTO_AUTH = False
AUTO_AUTH_USERNAME_PREFIX = 'auto_auth_'

SOCIAL_AUTH_STRATEGY = 'auth_backends.strategies.EdxDjangoStrategy'

# Set these to the correct values for your OAuth2 provider (e.g., LMS)
SOCIAL_AUTH_EDX_OAUTH2_KEY = 'enterprise-catalog-sso-key'
SOCIAL_AUTH_EDX_OAUTH2_SECRET = 'enterprise-catalog-sso-secret'
SOCIAL_AUTH_EDX_OAUTH2_URL_ROOT = 'http://127.0.0.1:8000'
SOCIAL_AUTH_EDX_OAUTH2_LOGOUT_URL = 'http://127.0.0.1:8000/logout'
BACKEND_SERVICE_EDX_OAUTH2_KEY = 'enterprise-catalog-backend-service-key'
BACKEND_SERVICE_EDX_OAUTH2_SECRET = 'enterprise-catalog-service-secret'

JWT_AUTH = {
    'JWT_AUTH_HEADER_PREFIX': 'JWT',
    'JWT_ISSUER': 'http://127.0.0.1:18000/oauth2',
    'JWT_ALGORITHM': 'HS256',
    'JWT_VERIFY_EXPIRATION': True,
    'JWT_PAYLOAD_GET_USERNAME_HANDLER': lambda d: d.get('preferred_username'),
    'JWT_LEEWAY': 1,
    'JWT_DECODE_HANDLER': 'edx_rest_framework_extensions.auth.jwt.decoder.jwt_decode_handler',
    'JWT_PUBLIC_SIGNING_JWK_SET': None,
    'JWT_AUTH_COOKIE': 'edx-jwt-cookie',
    'JWT_AUTH_COOKIE_HEADER_PAYLOAD': 'edx-jwt-cookie-header-payload',
    'JWT_AUTH_COOKIE_SIGNATURE': 'edx-jwt-cookie-signature',
    'JWT_AUTH_REFRESH_COOKIE': 'edx-jwt-refresh-cookie',
    'JWT_SECRET_KEY': 'SET-ME-PLEASE',
    # JWT_ISSUERS enables token decoding for multiple issuers (Note: This is not a native DRF-JWT field)
    # We use it to allow different values for the 'ISSUER' field, but keep the same SECRET_KEY and
    # AUDIENCE values across all issuers.
    'JWT_ISSUERS': [
        {
            'AUDIENCE': 'SET-ME-PLEASE',
            'ISSUER': 'http://localhost:18000/oauth2',
            'SECRET_KEY': 'SET-ME-PLEASE'
        },
    ],
}

# Request the user's permissions in the ID token
EXTRA_SCOPE = ['permissions']

LOGIN_REDIRECT_URL = '/api-docs/'
# END AUTHENTICATION CONFIGURATION


# OPENEDX-SPECIFIC CONFIGURATION
PLATFORM_NAME = 'Your Platform Name Here'
# END OPENEDX-SPECIFIC CONFIGURATION

# Set up logging for development use (logging to stdout)
LOGGING = get_logger_config(debug=DEBUG, dev_env=True)

EXTRA_APPS = []
CERTIFICATE_LANGUAGES = {
    'en': 'English',
    'es_419': 'Spanish'
}
ENTERPRISE_CATALOG_SERVICE_USER = 'enterprise_catalog_service_user'

"""############################# BEGIN CELERY ##################################"""

# Message configuration
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_COMPRESSION = 'gzip'
CELERY_RESULT_COMPRESSION = 'gzip'

# Events configuration
CELERY_TASK_TRACK_STARTED = True
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True

# Celery task routing configuration.
# Only the enterprise-catalog worker should receive enterprise-catalog tasks.
# Explicitly define these to avoid name collisions with other services
# using the same broker and the standard default queue name of "celery".
CELERY_TASK_DEFAULT_EXCHANGE = os.environ.get('CELERY_DEFAULT_EXCHANGE', 'enterprise_catalog')
CELERY_TASK_DEFAULT_ROUTING_KEY = os.environ.get('CELERY_DEFAULT_ROUTING_KEY', 'enterprise_catalog')
CELERY_TASK_DEFAULT_QUEUE = os.environ.get('CELERY_DEFAULT_QUEUE', 'enterprise_catalog.default')

# Celery Broker
# These settings need not be set if CELERY_TASK_ALWAYS_EAGER == True, like in Standalone.
# Devstack overrides these in its docker-compose.yml.
# Production environments can override these to be whatever they want.
CELERY_BROKER_TRANSPORT = os.environ.get('CELERY_BROKER_TRANSPORT', '')
CELERY_BROKER_HOSTNAME = os.environ.get('CELERY_BROKER_HOSTNAME', '')
CELERY_BROKER_VHOST = os.environ.get('CELERY_BROKER_VHOST', '')
CELERY_BROKER_USER = os.environ.get('CELERY_BROKER_USER', '')
CELERY_BROKER_PASSWORD = os.environ.get('CELERY_BROKER_PASSWORD', '')
CELERY_BROKER_URL = '{}://{}:{}@{}/{}'.format(
    CELERY_BROKER_TRANSPORT,
    CELERY_BROKER_USER,
    CELERY_BROKER_PASSWORD,
    CELERY_BROKER_HOSTNAME,
    CELERY_BROKER_VHOST
)

# Results configuration
CELERY_RESULT_BACKEND = 'django-db'
CELERY_TASK_IGNORE_RESULT = False
CELERY_TASK_STORE_ERRORS_EVEN_IF_IGNORED = True
# see https://github.com/celery/django-celery-results/issues/326
# on CELERY_RESULT_EXTENDED
CELERY_RESULT_EXTENDED = True

# Celery task time limits.
# Tasks will be asked to quit after 15 minutes...
CELERY_TASK_SOFT_TIME_LIMIT = 60 * 15
# ...and un-gracefully killed after 20.
CELERY_TASK_TIME_LIMIT = 60 * 20

# Propagate exceptions from eagerly applied tasks
CELERY_EAGER_PROPAGATES = True

CELERY_BROKER_TRANSPORT_OPTIONS = {
    'fanout_patterns': True,
    'fanout_prefix': True,
}

# Only allow each worker to run 100 tasks before restarting
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100

"""############################# END CELERY ##################################"""

MEDIA_STORAGE_BACKEND = {
    'DEFAULT_FILE_STORAGE': 'django.core.files.storage.FileSystemStorage',
    'MEDIA_ROOT': MEDIA_ROOT,
    'MEDIA_URL': MEDIA_URL
}
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SOCIAL_AUTH_REDIRECT_IS_HTTPS = False
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# How long we keep API Client data in cache. (seconds)
ONE_HOUR = 60 * 60
ENTERPRISE_CUSTOMER_CACHE_TIMEOUT = ONE_HOUR
DISCOVERY_CATALOG_QUERY_CACHE_TIMEOUT = ONE_HOUR
DISCOVERY_COURSE_DATA_CACHE_TIMEOUT = ONE_HOUR

# URLs
LMS_BASE_URL = os.environ.get('LMS_BASE_URL', '')
DISCOVERY_SERVICE_API_URL = os.environ.get('DISCOVERY_SERVICE_API_URL', '')
ENTERPRISE_LEARNER_PORTAL_BASE_URL = os.environ.get('ENTERPRISE_LEARNER_PORTAL_BASE_URL', '')
ECOMMERCE_BASE_URL = os.environ.get('ECOMMERCE_BASE_URL', '')
LICENSE_MANAGER_BASE_URL = os.environ.get('LICENSE_MANAGER_BASE_URL', '')

# Algolia
ALGOLIA = {
    'INDEX_NAME': '',
    'APPLICATION_ID': '',
    'API_KEY': '',
}

# Which fields should be plucked from the /search/all course-discovery API
# response in `update_catalog_metadata_task` for course content metadata?
COURSE_FIELDS_TO_PLUCK_FROM_SEARCH_ALL = os.environ.get(
    'COURSE_FIELDS_TO_PLUCK_FROM_SEARCH_ALL',
    DEFAULT_COURSE_FIELDS_TO_PLUCK_FROM_SEARCH_ALL,
)

# Set up system-to-feature roles mapping for edx-rbac
SYSTEM_TO_FEATURE_ROLE_MAPPING = {
    # The enterprise catalog admin role is for users who need to perform state altering requests on catalogs
    SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE: [ENTERPRISE_CATALOG_ADMIN_ROLE],
    SYSTEM_ENTERPRISE_OPERATOR_ROLE: [ENTERPRISE_CATALOG_ADMIN_ROLE],
    # Admins and learners should both be able to access catalog metadata and call the contains content endpoints
    SYSTEM_ENTERPRISE_LEARNER_ROLE: [ENTERPRISE_CATALOG_LEARNER_ROLE],
    SYSTEM_ENTERPRISE_ADMIN_ROLE: [ENTERPRISE_CATALOG_LEARNER_ROLE, ENTERPRISE_CATALOG_ADMIN_ROLE],
}

# Set the query batch size with which existing content metadata records
# are updated during the `update_catalog_metadata_task()` celery task.
# Note that we may have some content metadata records
# that are relatively large - perhaps as large as 1MB.
# You'll have to take the `max_allowed_packet` size of the MySQL
# server configuration into account when determining the
# value of the setting below.
UPDATE_EXISTING_CONTENT_METADATA_BATCH_SIZE = 4

USE_DEPRECATED_PYTZ = True

# (ENT-5968) This is temporary until offers are implemented in the learner portal
INTEGRATED_CUSTOMERS_WITH_SUBSIDIES_AND_OFFERS = ['731b28ee-09d1-4b89-8f7b-2c8fd0939746']
