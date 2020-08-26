"""
Constants for each API Client.
"""
from urllib.parse import urljoin

from django.conf import settings


# Discovery API Client Constants
SEARCH_ALL_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, 'search/all/')
COURSES_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, 'courses/')
OFFSET_SIZE = 100

# Enterprise API Client Constants
ENTERPRISE_API_URL = urljoin(settings.LMS_BASE_URL, '/enterprise/api/v1/')
ENTERPRISE_CUSTOMER_ENDPOINT = urljoin(ENTERPRISE_API_URL, 'enterprise-customer/')
