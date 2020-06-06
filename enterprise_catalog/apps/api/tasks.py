import logging

from celery import shared_task

from enterprise_catalog.apps.api.v1.utils import (
    add_uuids_to_courses,
    create_algolia_objects_from_courses,
    initialize_algolia_index,
)
from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.models import (
    get_related_enterprise_catalogs_for_content_keys,
    update_contentmetadata_from_discovery,
)


logger = logging.getLogger(__name__)


@shared_task(bind=True)
# pylint: disable=unused-argument
def index_enterprise_catalog_courses_in_algolia(self, content_keys, index_name, app_id, api_key, algolia_fields):
    """
    Index a batch of course content into Algolia.

    Arguments:
        content_keys (list): a list of content_keys to index in Algolia
        index_name (str): name of an Algolia index
        app_id (str): an APPLICATION_ID for Algolia
        api_key (str): an API_KEY for Algolia
    """
    algolia_index = initialize_algolia_index(index_name, app_id, api_key)
    if not algolia_index:
        # without an Algolia index, we can't really do much of anything so exit early
        return

    discovery_client = DiscoveryApiClient()
    query_params = {
        'keys': ','.join(content_keys),
        'limit': 100,
        'ordering': 'key',
    }
    courses = discovery_client.get_courses(query_params=query_params)
    logger.info(
        'Retrieved %d courses from course-discovery for %d content keys: %s',
        len(courses),
        len(content_keys),
        content_keys,
    )

    if courses is not None:
        # Get related enterprise_catalog_uuids and enterprise_customer_uuids for the provided content_keys
        related_enterprise_catalogs = get_related_enterprise_catalogs_for_content_keys(content_keys)
        for content_key, uuids in related_enterprise_catalogs.items():
            # add those enterprise-specific uuids to the appropriate course object within the list of courses
            courses = add_uuids_to_courses(content_key, uuids, courses)

        # create objects to send to Algolia by extracting only the fields we care about
        algolia_objects = create_algolia_objects_from_courses(courses, algolia_fields)

        try:
            # Add algolia_objects to the Algolia index
            response = algolia_index.partial_update_objects(algolia_objects, {
                'createIfNotExists': True,
            })
            object_ids = []
            for response in response.raw_responses:
                object_ids += response.get('objectIDs', [])
            logger.info(
                'Successfully indexed %d (%d unique) courses in Algolia\'s %s index: %s',
                len(object_ids),
                len(set(object_ids)),
                index_name,
                object_ids,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                'Could not index %d course(s) in Algolia\'s %s index: %s',
                len(algolia_objects),
                index_name,
                exc,
            )
    else:
        logger.error(
            'No courses retrieved from course-discovery for content keys: %s',
            content_keys,
        )


@shared_task(bind=True)
# pylint: disable=unused-argument
def update_catalog_metadata_task(self, catalog_query_id):
    update_contentmetadata_from_discovery(catalog_query_id)
