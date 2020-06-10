import copy
import logging

from celery import shared_task
from celery_utils.logged_task import LoggedTask

from enterprise_catalog.apps.api.v1.utils import (
    create_algolia_objects_from_courses,
    find_index_in_courses_for_content_key,
    get_algolia_object_id,
)
from enterprise_catalog.apps.api_client.algolia import AlgoliaSearchClient
from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.models import (
    get_related_enterprise_catalogs_for_content_keys,
    update_contentmetadata_from_discovery,
)


logger = logging.getLogger(__name__)


@shared_task(base=LoggedTask)
def index_enterprise_catalog_courses_in_algolia(content_keys, algolia_fields):
    """
    Index a batch of course content into Algolia.

    Arguments:
        content_keys (list): a list of content_keys to index in Algolia
        algolia_fields (list): list of course fields we want to index in Algolia
    """
    # initialize Algolia index
    algolia_client = AlgoliaSearchClient()
    algolia_client.init_index()

    query_params = {
        'keys': ','.join(content_keys),
        'ordering': 'key',
    }
    try:
        discovery_client = DiscoveryApiClient()
        courses = discovery_client.get_courses(query_params=query_params)
    except Exception:  # pylint: disable=broad-except
        courses = None

    logger.info(
        'Retrieved %d courses from course-discovery for %d content keys: %s',
        len(courses),
        len(content_keys),
        content_keys,
    )

    if not courses:
        logger.error(
            'No courses retrieved from course-discovery for content keys: %s',
            content_keys,
        )
        return

    # Get related enterprise_catalog_uuids and enterprise_customer_uuids for the provided content_keys
    related_enterprise_catalogs = get_related_enterprise_catalogs_for_content_keys(content_keys)

    for content_key, uuids in related_enterprise_catalogs.items():
        # add those enterprise-specific uuids to the appropriate course object within the list of courses
        course_index = find_index_in_courses_for_content_key(content_key, courses)
        if course_index is not None:
            course = copy.deepcopy(courses[course_index])
            course.update({
                'objectID': get_algolia_object_id(course['uuid']),
                'enterprise_catalog_uuids': uuids.get('enterprise_catalog_uuids', []),
                'enterprise_customer_uuids': uuids.get('enterprise_customer_uuids', []),
            })
            courses[course_index] = course
        else:
            logger.error(
                'Could not find content_key "%s" in list of %d courses.',
                content_key,
                len(content_keys),
            )

    # extract out only the fields we care about and send to Algolia index
    algolia_objects = create_algolia_objects_from_courses(courses, algolia_fields)
    algolia_client.partially_update_index(algolia_objects)


@shared_task(base=LoggedTask)
def update_catalog_metadata_task(catalog_query_id):
    update_contentmetadata_from_discovery(catalog_query_id)
