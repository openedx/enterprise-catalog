"""
Constants for each API Client.
"""
from urllib.parse import urljoin

from django.conf import settings


# Discovery API Client Constants
DISCOVERY_SEARCH_ALL_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, 'search/all/')
DISCOVERY_COURSES_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, 'courses/')
DISCOVERY_PROGRAMS_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, 'programs/')
DISCOVERY_OFFSET_SIZE = 200
DISCOVERY_CATALOG_QUERY_CACHE_KEY_TPL = 'catalog_query:{id}'

# Enterprise API Client Constants
ENTERPRISE_API_URL = urljoin(settings.LMS_BASE_URL, '/enterprise/api/v1/')
ENTERPRISE_CUSTOMER_ENDPOINT = urljoin(ENTERPRISE_API_URL, 'enterprise-customer/')
ENTERPRISE_CUSTOMER_CACHE_KEY_TPL = 'customer:{uuid}'

# Ecommerce API Client Constants
COUPONS_OVERVIEW_ENDPOINT = urljoin(
    settings.ECOMMERCE_BASE_URL,
    '/api/v2/enterprise/coupons/{enterprise_customer_uuid}/overview/'
)

# License-manager API Client constants
CUSTOMER_AGREEMENT_ENDPOINT = urljoin(settings.LICENSE_MANAGER_BASE_URL, '/api/v1/customer-agreement/')
