import copy
import logging

from celery import shared_task
from celery_utils.logged_task import LoggedTask

from enterprise_catalog.apps.api.v1.utils import (
    create_algolia_objects_from_courses,
    get_algolia_object_id,
)
from enterprise_catalog.apps.api_client.algolia import AlgoliaSearchClient
from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    course_metadata_used_by_at_least_one_catalog,
    related_enterprise_catalogs_for_content_metadata,
    update_contentmetadata_from_discovery,
)


logger = logging.getLogger(__name__)


@shared_task(base=LoggedTask)
def update_full_content_metadata_task(*args, **kwargs):  # pylint: disable=unused-argument
    """
    Traverse discovery's /api/v1/courses endpoint to fetch the full course metadata of all ContentMetadata
    records with a content type of "course". The course metadata is merged with the existing contents of
    the json_metadata field for each ContentMetadata record.
    """
    discovery_client = DiscoveryApiClient()

    # fetch all courses from course-discovery
    query_params = {'ordering': 'key'}
    courses = discovery_client.get_courses(query_params=query_params)

    if not courses:
        logger.error('No courses were retrieved from course-discovery.')
        return

    logger.info('Retrieved %d courses from course-discovery.', len(courses))

    # find all ContentMetadata records with a content type of "course" that are
    # also part of at least one EnterpriseCatalog
    content_metadata = course_metadata_used_by_at_least_one_catalog()

    content_keys = [metadata.content_key for metadata in content_metadata]
    courses_in_content_metadata = [course for course in courses if course.get('key') in content_keys]

    if not courses_in_content_metadata:
        logger.error('Could not find any ContentMetadata records that match courses retrieved from course-discovery.')
        return

    logger.info(
        'Found %d ContentMetadata records that match courses retrieved from course-discovery.',
        len(courses_in_content_metadata),
    )

    # iterate through the matching courses to update the json_metadata field, replacing
    # the minimal json_metadata retrieved by /search/all/ with the full json_metadata
    # retrieved by /courses/.
    updated_metadata = []
    for course_metadata in courses_in_content_metadata:
        content_key = course_metadata.get('key')
        try:
            metadata_record = ContentMetadata.objects.get(content_key=content_key)
        except ContentMetadata.DoesNotExist:
            logger.error('Could not find ContentMetadata record for content_key %s.', content_key)
            continue

        # merge the original json_metadata with the full course_metadata to ensure
        # we're not removing any critical fields, e.g. "aggregation_key".
        json_metadata = metadata_record.json_metadata.copy()
        json_metadata.update(course_metadata)
        metadata_record.json_metadata = json_metadata
        updated_metadata.append(metadata_record)

    ContentMetadata.objecs.bulk_update(updated_metadata, ['json_metadata'])

    logger.info(
        'Successfully updated %d of %d ContentMetadata records with full metadata from course-discovery.',
        len(updated_metadata),
        len(courses_in_content_metadata),
    )


@shared_task(base=LoggedTask)
def index_enterprise_catalog_courses_in_algolia_task(algolia_fields, algolia_settings):
    """
    Index course data in Algolia with enterprise-related fields.

    Arguments:
        algolia_fields (list): list of course fields we want to index in Algolia
        algolia_settings (dict): dictionary of default Algolia index settings
    """
    if not algolia_fields or not algolia_settings:
        logger.error('Must provide algolia_fields and algolia_settings as arguments.')
        return

    # initialize the Algolia index
    algolia_client = AlgoliaSearchClient()
    algolia_client.init_index()

    # configure the Algolia index
    algolia_client.set_index_settings(algolia_settings)

    # find all ContentMetadata records with a content type of "course" that are
    # also part of at least one EnterpriseCatalog
    content_metadata = course_metadata_used_by_at_least_one_catalog()

    # find related enterprise_catalog_uuids and enterprise_customer_uuids for each ContentMetadata record
    related_enterprise_catalogs = related_enterprise_catalogs_for_content_metadata(content_metadata)

    courses = []
    for content_key, uuids in related_enterprise_catalogs.items():
        try:
            metadata_record = ContentMetadata.objects.get(content_key=content_key)
        except ContentMetadata.DoesNotExist:
            logger.error('Could not find ContentMetadata record for content_key %s.', content_key)
            continue

        # add enterprise-related uuids to json_metadata and append to list of courses
        json_metadata = copy.deepcopy(metadata_record.json_metadata)
        json_metadata.update({
            'objectID': get_algolia_object_id(json_metadata.get('uuid')),
            'enterprise_catalog_uuids': uuids.get('enterprise_catalog_uuids', []),
            'enterprise_customer_uuids': uuids.get('enterprise_customer_uuids', []),
        })
        courses.append(json_metadata)

    # extract out only the fields we care about and send to Algolia index
    algolia_objects = create_algolia_objects_from_courses(courses, algolia_fields)
    algolia_client.partially_update_index(algolia_objects)


@shared_task(base=LoggedTask)
def update_catalog_metadata_task(catalog_query_id):
    update_contentmetadata_from_discovery(catalog_query_id)
