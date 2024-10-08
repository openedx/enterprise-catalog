"""
Discovery service api client code.
"""
import logging
import time

import requests
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings

from enterprise_catalog.apps.catalog.constants import (
    DISCOVERY_COURSE_KEY_BATCH_SIZE,
    DISCOVERY_PROGRAM_KEY_BATCH_SIZE,
)
from enterprise_catalog.apps.catalog.content_metadata_utils import (
    tansform_force_included_courses,
)
from enterprise_catalog.apps.catalog.utils import batch

from .base_oauth import BaseOAuthClient
from .constants import (
    DISCOVERY_COURSE_REVIEWS_ENDPOINT,
    DISCOVERY_COURSES_ENDPOINT,
    DISCOVERY_OFFSET_SIZE,
    DISCOVERY_PROGRAMS_ENDPOINT,
    DISCOVERY_SEARCH_ALL_ENDPOINT,
    DISCOVERY_VIDEO_SKILLS_ENDPOINT,
)


LOGGER = logging.getLogger(__name__)


class DiscoveryApiClient(BaseOAuthClient):
    """
    Object builds an API client to make calls to the Discovery Service.
    """

    # the maximum number of retries to attempt a call
    MAX_RETRIES = getattr(settings, "ENTERPRISE_DISCOVERY_CLIENT_MAX_RETRIES", 4)
    # the number of seconds to sleep beteween tries, which is doubled every attempt
    BACKOFF_FACTOR = getattr(settings, "ENTERPRISE_DISCOVERY_CLIENT_BACKOFF_FACTOR", 2)
    # the number of seconds to wait for a response
    HTTP_TIMEOUT = getattr(settings, "ENTERPRISE_DISCOVERY_CLIENT_TIMEOUT", 15)

    def _calculate_backoff(self, attempt_count):
        """
        Calculate the seconds to sleep based on attempt_count
        """
        return (self.BACKOFF_FACTOR * (2 ** (attempt_count - 1)))

    def _retrieve_metadata_page_for_content_filter(self, content_filter, page, request_params):
        """
        Makes a request to discovery's /search/all/ endpoint with the specified
        content_filter, page, and request_params
        """
        LOGGER.info(f'Retrieving results from course-discovery for page {page}...')
        attempts = 0
        request_params_with_page = request_params | {'page': page}
        while True:
            attempts = attempts + 1
            successful = True
            exception = None
            try:
                response = self.client.post(
                    DISCOVERY_SEARCH_ALL_ENDPOINT,
                    json=content_filter,
                    params=request_params_with_page,
                    timeout=self.HTTP_TIMEOUT,
                )
                successful = response.status_code < 400
                elapsed_seconds = response.elapsed.total_seconds()
                LOGGER.info(
                    f'Retrieved results from course-discovery for page {page} in '
                    f'retrieve_metadata_for_content_filter_seconds={elapsed_seconds} seconds.'
                )
            except requests.exceptions.RequestException as err:
                exception = err
                LOGGER.exception(f'Error while retrieving results from course-discovery for page {page}')
                successful = False
            if attempts <= self.MAX_RETRIES and not successful:
                sleep_seconds = self._calculate_backoff(attempts)
                LOGGER.warning(
                    f'failed request detected from {DISCOVERY_SEARCH_ALL_ENDPOINT}, '
                    'backing-off before retrying, '
                    f'sleeping {sleep_seconds} seconds...'
                )
                time.sleep(sleep_seconds)
            else:
                if exception:
                    raise exception
                break
        try:
            return response.json()
        except requests.exceptions.JSONDecodeError as err:
            LOGGER.exception(
                f'Invalid JSON while retrieving results from course-discovery for page {page}, '
                f'resonse status code: {response.status_code}, '
                f'response body: {response.text}'
            )
            raise err

    def retrieve_metadata_for_content_filter(self, content_filter, request_params):
        """
        """
        request_params_customized = request_params | {
            # Increase number of results per page for the course-discovery response
            'page_size': 100,
            # Ensure paginated results are consistently ordered by `aggregation_key` and `start`
            'ordering': 'aggregation_key,start',
        }
        page = 1
        results = []
        try:
            response = self._retrieve_metadata_page_for_content_filter(content_filter, page, request_params_customized)
            results += response.get('results', [])
            # Traverse all pages and concatenate results
            while response.get('next'):
                page += 1
                response = self._retrieve_metadata_page_for_content_filter(content_filter, page, request_params_customized)
                results += response.get('results', [])
        except Exception as exc:
            LOGGER.exception(
                'Could not retrieve content items from course-discovery (page %s): %s',
                page,
                exc,
            )
            raise exc
        return results

    def _retrieve_course_reviews(self, request_params):
        """
        Makes a request to discovery's /api/v1/course_review/ paginated endpoint
        """
        page = request_params.get('page', 1)
        LOGGER.info(f'Retrieving course reviews from course-discovery for page {page}...')
        attempts = 0
        while True:
            attempts = attempts + 1
            successful = True
            exception = None
            try:
                response = self.client.get(
                    DISCOVERY_COURSE_REVIEWS_ENDPOINT,
                    params=request_params,
                    timeout=self.HTTP_TIMEOUT,
                )
                successful = response.status_code < 400
                elapsed_seconds = response.elapsed.total_seconds()
                LOGGER.info(
                    f'Retrieved course review results from course-discovery for page {page} in '
                    f'retrieve_course_reviews_seconds={elapsed_seconds} seconds.'
                )
            except requests.exceptions.RequestException as err:
                exception = err
                LOGGER.exception(f'Error while retrieving course review results from course-discovery for page {page}')
                successful = False
            if attempts <= self.MAX_RETRIES and not successful:
                sleep_seconds = self._calculate_backoff(attempts)
                LOGGER.warning(
                    f'failed request detected from {DISCOVERY_SEARCH_ALL_ENDPOINT}, '
                    'backing-off before retrying, '
                    f'sleeping {sleep_seconds} seconds...'
                )
                time.sleep(sleep_seconds)
            else:
                if exception:
                    raise exception
                break
        try:
            return response.json()
        except requests.exceptions.JSONDecodeError as err:
            LOGGER.exception(
                f'Invalid JSON while retrieving course review results from course-discovery for page {page}, '
                f'resonse status code: {response.status_code}, '
                f'response body: {response.text}'
            )
            raise err

    def get_course_reviews(self, course_keys=None):
        """
        Return results from the discovery service's /course_review endpoint as an object of key = course key, value =
        course review. If course_keys is specified, only return results for those course keys.
        """
        page = 1
        results = []
        request_params = {'page': page}
        try:
            response = self._retrieve_course_reviews(request_params)
            results += response.get('results', [])
            # Traverse all pages and concatenate results
            while response.get('next'):
                page += 1
                request_params.update({'page': page})
                response = self._retrieve_course_reviews(request_params)
                results += response.get('results', [])
        except Exception as exc:
            LOGGER.exception(f'Could not retrieve course reviews from course-discovery (page {page}) {exc}')
            raise exc

        results = {
            result.get('course_key'): result for result in results if (
                course_keys is None or result.get('course_key') in course_keys
            )
        }

        return results

    def _retrieve_video_skills(self, request_params):
        """
        Makes a request to discovery's taxonomy/api/v1/xblocks paginated endpoint
        """
        page = request_params.get('page', 1)
        LOGGER.info(f'Retrieving video skills from course-discovery for page {page}...')
        attempts = 0
        while True:
            attempts = attempts + 1
            successful = True
            exception = None
            try:
                response = self.client.get(
                    DISCOVERY_VIDEO_SKILLS_ENDPOINT,
                    params=request_params,
                    timeout=self.HTTP_TIMEOUT,
                )
                successful = response.status_code < 400
                elapsed_seconds = response.elapsed.total_seconds()
                LOGGER.info(
                    f'Retrieved video skills results from course-discovery for page {page} in '
                    f'retrieve_video_skills_seconds={elapsed_seconds} seconds.'
                )
            except requests.exceptions.RequestException as err:
                exception = err
                LOGGER.exception(f'Error while retrieving video skills results from course-discovery for page {page}')
                successful = False
            if attempts <= self.MAX_RETRIES and not successful:
                sleep_seconds = self._calculate_backoff(attempts)
                LOGGER.warning(
                    f'failed request detected from {DISCOVERY_VIDEO_SKILLS_ENDPOINT}, '
                    'backing-off before retrying, '
                    f'sleeping {sleep_seconds} seconds...'
                )
                time.sleep(sleep_seconds)
            else:
                if exception:
                    raise exception
                break
        try:
            return response.json()
        except requests.exceptions.JSONDecodeError as err:
            LOGGER.exception(
                f'Invalid JSON while retrieving video skills results from course-discovery for page {page}, '
                f'resonse status code: {response.status_code}, '
                f'response body: {response.text}'
            )
            raise err

    def get_video_skills(self, video_usage_key):
        """
        Return results from the discovery service's taxonomy/api/v1/xblocks endpoint
        """
        page = 1
        results = []
        request_params = {'page': page, 'usage_key': video_usage_key, 'verified': 'false'}
        try:
            response = self._retrieve_video_skills(request_params)
            results += response.get('results', [])
            # Traverse all pages and concatenate results
            while response.get('next'):
                page += 1
                request_params.update({'page': page})
                response = self._retrieve_video_skills(request_params)
                results += response.get('results', [])
        except Exception as exc:
            LOGGER.exception(f'Could not retrieve video skills from course-discovery (page {page}) {exc}')
            raise exc
        video_skills = []
        for result in results:
            video_skills += result.get('skills')

        return video_skills

    def get_metadata_by_query(self, catalog_query, extra_query_params=None):
        """
        Return results from the discovery service's search/all endpoint.

        Arguments:
            catalog_query (CatalogQuery): Catalog Query object to retrieve metadata for

        Returns:
            list: a list of the results, or None if there was an error calling the discovery service.
        """
        request_params = {
            # Omit non-active course runs from the course-discovery results
            'exclude_expired_course_run': True,
            # Ensure to fetch learner pathways as part of search/all endpoint response.
            'include_learner_pathways': True,
        } | extra_query_params
        results = []

        try:
            content_filter = catalog_query.content_filter
            results.extend(self.retrieve_metadata_for_content_filter(content_filter, request_params))
        except Exception as exc:
            LOGGER.exception(
                'Could not retrieve content items for catalog query %s: %s',
                catalog_query,
                exc,
            )
            raise exc

        try:
            # NOTE johnnagro this ONLY supports courses at the moment (NOT programs, leanerpathways, etc)
            if forced_aggregation_keys := catalog_query.content_filter.get('enterprise_force_include_aggregation_keys'):
                LOGGER.info(
                    'get_metadata_by_query enterprise_force_include_aggregation_keys seen'
                    f'attempting to force-include: {forced_aggregation_keys}'
                )
                forced_courses = self.fetch_courses_by_keys(forced_aggregation_keys)
                results += tansform_force_included_courses(forced_courses)
        except Exception as exc:
            LOGGER.exception(
                f'unable to add unlisted courses for catalog_id: {catalog_query.id}'
            )
            raise exc

        return results

    def _retrieve_courses(self, offset, request_params):
        """
        Makes a request to discovery's /api/v1/courses/ endpoint with the specified offset and request_params
        """
        LOGGER.info('Retrieving courses from course-discovery for offset %s...', offset)
        response = self.client.get(
            DISCOVERY_COURSES_ENDPOINT,
            params=request_params,
            timeout=self.HTTP_TIMEOUT,
        ).json()
        return response

    def get_courses(self, query_params=None):
        """
        Return results from the discovery service's /courses endpoint.

        Arguments:
            query_params (dict): additional query params for the rest api endpoint
                we're hitting. e.g. - {'limit': 100}

        Returns:
            list: a list of the results, or None if there was an error calling the discovery service.
        """
        request_params = {
            'ordering': 'key',
            'limit': DISCOVERY_OFFSET_SIZE,
        }
        request_params.update(query_params or {})

        courses = []
        offset = 0
        try:
            response = self._retrieve_courses(offset, request_params)
            courses += response.get('results')
            # Traverse all pages and concatenate results
            while response.get('next'):
                offset += DISCOVERY_OFFSET_SIZE
                request_params.update({'offset': offset})
                response = self._retrieve_courses(offset, request_params)
                courses += response.get('results', [])
        except SoftTimeLimitExceeded as exc:
            LOGGER.warning(
                'A task reached the soft time limit while traversing courses. %d courses already retrieved'
                ' from course-discovery will continue to be processed: %s',
                len(courses),
                exc,
            )
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.error(
                'Could not get courses from course-discovery (offset %d) with query params %s: %s',
                offset,
                request_params,
                exc,
            )

        return courses

    def _retrieve_programs(self, offset, request_params):
        """
        Makes a request to discovery's /api/v1/programs/ endpoint with the specified offset and request_params
        """
        LOGGER.info('Retrieving programs from course-discovery for offset %s...', offset)
        response = self.client.get(
            DISCOVERY_PROGRAMS_ENDPOINT,
            params=request_params,
            timeout=self.HTTP_TIMEOUT,
        ).json()
        return response

    def get_programs(self, query_params=None):
        """
        Return results from the discovery service's /programs endpoint.

        Arguments:
            query_params (dict): additional query params for the rest api endpoint
                we're hitting. e.g. - {'limit': 100}

        Returns:
            list: a list of the results, or None if there was an error calling the discovery service.
        """
        request_params = {
            'ordering': 'key',
            'limit': DISCOVERY_OFFSET_SIZE,
            'extended': 'True',
        }
        request_params.update(query_params or {})

        programs = []
        offset = 0
        try:
            response = self._retrieve_programs(offset, request_params)
            programs += response.get('results')
            # Traverse all pages and concatenate results
            while response.get('next'):
                offset += DISCOVERY_OFFSET_SIZE
                request_params.update({'offset': offset})
                response = self._retrieve_programs(offset, request_params)
                programs += response.get('results', [])
        except SoftTimeLimitExceeded as exc:
            LOGGER.warning(
                'A task reached the soft time limit while traversing programs. %d programs already retrieved'
                ' from course-discovery will continue to be processed: %s',
                len(programs),
                exc,
            )
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.error(
                'Could not get programs from course-discovery (offset %d) with query params %s: %s',
                offset,
                request_params,
                exc,
            )

        return programs

    def fetch_courses_by_keys(self, course_keys):
        """
        Fetches course data from discovery's /api/v1/courses endpoint for the provided course keys.

        Args:
            course_keys (list of str): Content keys for Course ContentMetadata objects.
        Returns:
            list of dict: Returns a list of dictionaries where each dictionary represents the course
            data from discovery.
        """
        courses = []

        # Batch the course keys into smaller chunks so that we don't send too big of a request to discovery
        batched_course_keys = batch(course_keys, batch_size=DISCOVERY_COURSE_KEY_BATCH_SIZE)
        for course_keys_chunk in batched_course_keys:
            # Discovery expects the keys param to be in the format ?keys=course1,course2,...
            query_params = {'keys': ','.join(course_keys_chunk)}
            courses.extend(self.get_courses(query_params=query_params))

        return courses

    def fetch_programs_by_keys(self, program_keys):
        """
        Fetches program data from discovery's /api/v1/programs endpoint for the provided program keys.

        Args:
            program_keys (list of str): Content keys for Program ContentMetadata objects.
        Returns:
            list of dict: Returns a list of dictionaries where each dictionary represents the program
            data from discovery.
        """
        programs = []

        # Batch the program keys into smaller chunks so that we don't send too big of a request to discovery
        batched_program_keys = batch(program_keys, batch_size=DISCOVERY_PROGRAM_KEY_BATCH_SIZE)
        for program_keys_chunk in batched_program_keys:
            # Discovery expects the uuids param to be in the format ?uuids=program1,program2,...
            query_params = {'uuids': ','.join(program_keys_chunk)}
            programs.extend(self.get_programs(query_params=query_params))

        return programs


class CatalogQueryMetadata:
    """
    Metadata for a given CatalogQuery from the Discovery API.

    """
    def __init__(self, catalog_query):
        """
        Initialize a Catalog Query details instance and load data from
        the Discovery API client.

        Arguments:
            catalog_query (CatalogQuery): Catalog Query to retrieve metadata for
        """
        self.catalog_query = catalog_query
        self.catalog_query_data = self._get_catalog_query_metadata(catalog_query)

    @property
    def metadata(self):
        """
        Return catalog query metadata (will be an empty dict if unavailable)
        """
        return self.catalog_query_data

    def _get_catalog_query_metadata(self, catalog_query):
        """
        Retrieve JSON data containing Catalog Query metadata for the given catalog_query_id
        by making a call to Discovery API Client.

        Arguments:
            catalog_query (CatalogQuery): Catalog Query object

        Returns:
            customer_data (dict): Enterprise Customer details OR
                Empty dictionary if no data found from API.
        """
        client = DiscoveryApiClient()
        catalog_query_data = client.get_metadata_by_query(catalog_query)
        return catalog_query_data
