"""
Constants for each API Client.
"""
from urllib.parse import urljoin

from django.conf import settings


# Discovery API Client Constants
DISCOVERY_SEARCH_ALL_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, 'search/all/')
DISCOVERY_COURSES_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, 'courses/')
DISCOVERY_PROGRAMS_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, 'programs/')
DISCOVERY_COURSE_REVIEWS_ENDPOINT = urljoin(settings.DISCOVERY_SERVICE_API_URL, 'course_review/')
DISCOVERY_VIDEO_SKILLS_ENDPOINT = 'https://discovery.edx.org/taxonomy/api/v1/xblocks/'
DISCOVERY_OFFSET_SIZE = 200
DISCOVERY_CATALOG_QUERY_CACHE_KEY_TPL = 'catalog_query:{id}'
DISCOVERY_AVERAGE_COURSE_REVIEW_CACHE_KEY = 'average_course_review'

COURSE_REVIEW_BAYESIAN_CONFIDENCE_NUMBER = 15

# As of 1/26/24 this is calculated from Snowflake:
# SELECT SUM(REVIEWS_COUNT * AVG_COURSE_RATING)/SUM(REVIEWS_COUNT) FROM enterprise.course_reviews
COURSE_REVIEW_BASE_AVG_REVIEW_SCORE = 4.5

# Enterprise API Client Constants
ENTERPRISE_API_URL = urljoin(settings.LMS_BASE_URL, '/enterprise/api/v1/')
ENTERPRISE_CUSTOMER_ENDPOINT = urljoin(ENTERPRISE_API_URL, 'enterprise-customer/')
ENTERPRISE_CUSTOMER_CACHE_KEY_TPL = 'customer:{uuid}'
STUDIO_API_COURSE_VIDEOS_ENDPOINT = urljoin(settings.STUDIO_BASE_URL, '/api/contentstore/v1/videos/{course_run_key}')
STUDIO_API_VIDEOS_LOCATION_ENDPOINT = urljoin(
    settings.STUDIO_BASE_URL,
    '/api/contentstore/v1/videos/{course_run_key}/{edx_video_id}/usage'
)

# Ecommerce API Client Constants
COUPONS_OVERVIEW_ENDPOINT = urljoin(
    settings.ECOMMERCE_BASE_URL,
    '/api/v2/enterprise/coupons/{enterprise_customer_uuid}/overview/'
)

# License-manager API Client constants
CUSTOMER_AGREEMENT_ENDPOINT = urljoin(settings.LICENSE_MANAGER_BASE_URL, '/api/v1/customer-agreement/')
