import copy
import logging

from celery import shared_task
from celery_utils.logged_task import LoggedTask
from django.db.models import Q

from enterprise_catalog.apps.api.v1.utils import (
    create_algolia_objects_from_courses,
    get_algolia_object_id,
)
from enterprise_catalog.apps.api_client.algolia import AlgoliaSearchClient
from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    content_metadata_with_type_course,
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

    # find all ContentMetadata records with a content type of "course"
    content_metadata = content_metadata_with_type_course()

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

    ContentMetadata.objects.bulk_update(updated_metadata, ['json_metadata'], batch_size=10)

    logger.info(
        'Successfully updated %d of %d ContentMetadata records with full metadata from course-discovery.',
        len(updated_metadata),
        len(courses_in_content_metadata),
    )


@shared_task(base=LoggedTask)
def index_enterprise_catalog_courses_in_algolia_task(algolia_fields, content_keys):
    """
    Index course data in Algolia with enterprise-related fields.

    Arguments:
        algolia_fields (list): list of course fields we want to index in Algolia
        content_keys (list): list of content_keys
    """
    if not algolia_fields or not content_keys:
        logger.error('Must provide algolia_fields and content_keys as arguments.')
        return

    # initialize the Algolia index
    algolia_client = AlgoliaSearchClient()
    algolia_client.init_index()

    courses = []
    enterprise_uuids_for_courses = {}

    # retrieve ContentMetadata records that match the specified content_keys in the
    # content_key or parent_content_key. returns both courses and course runs.
    query = Q(content_key__in=content_keys) | Q(parent_content_key__in=content_keys)
    content_metadata = ContentMetadata.objects.filter(query)

    # iterate through ContentMetadata records, retrieving the enterprise_catalog_uuids
    # and enterprise_customer_uuids associated with each ContentMetadata record (either
    # a course or a course run), storing them in a dictionary with the related course's
    # content_key as a key for later retrieval. the course's content_key is determined by
    # the content_key field if the metadata is a `COURSE` or by the parent_content_key
    # field if the metadata is a `COURSE_RUN`.
    for metadata in content_metadata:
        is_course_content_type = metadata.content_type == COURSE
        course_content_key = metadata.content_key if is_course_content_type else metadata.parent_content_key
        associated_queries = metadata.catalog_queries.all()
        enterprise_catalog_uuids = set()
        enterprise_customer_uuids = set()
        for query in associated_queries:
            associated_catalogs = query.enterprise_catalogs.values('uuid', 'enterprise_uuid')
            for catalog in associated_catalogs:
                enterprise_catalog_uuids.add(str(catalog['uuid']))
                enterprise_customer_uuids.add(str(catalog['enterprise_uuid']))

        existing_uuids = copy.deepcopy(enterprise_uuids_for_courses.get(course_content_key, {}))

        # add to any existing enterprise catalog uuids
        existing_catalog_uuids = existing_uuids.get('enterprise_catalog_uuids', set())
        existing_uuids['enterprise_catalog_uuids'] = existing_catalog_uuids.union(enterprise_catalog_uuids)

        # add to any existing enterprise customer uuids
        existing_customer_uuids = existing_uuids.get('enterprise_customer_uuids', set())
        existing_uuids['enterprise_customer_uuids'] = existing_customer_uuids.union(enterprise_customer_uuids)

        # replace the enterprise-related uuids with the updates ones for the course
        enterprise_uuids_for_courses[course_content_key] = existing_uuids

    # iterate through only the courses, retrieving the enterprise-related uuids from the
    # dictionary created above, and append each course to the list of courses with the added
    # fields (e.g., objectID, enterprise_customer_uuids).
    course_content_metadata = content_metadata.filter(content_type=COURSE)
    for metadata in course_content_metadata:
        content_key = metadata.content_key
        enterprise_uuids = enterprise_uuids_for_courses[content_key]
        # add enterprise-related uuids to json_metadata
        json_metadata = copy.deepcopy(metadata.json_metadata)
        json_metadata.update({
            'objectID': get_algolia_object_id(json_metadata.get('uuid')),
            'enterprise_catalog_uuids': sorted(list(enterprise_uuids.get('enterprise_catalog_uuids', {}))),
            'enterprise_customer_uuids': sorted(list(enterprise_uuids.get('enterprise_customer_uuids', {}))),
        })
        courses.append(json_metadata)

    # extract out only the fields we care about and send to Algolia index
    algolia_objects = create_algolia_objects_from_courses(courses, algolia_fields)
    algolia_client.partially_update_index(algolia_objects)


@shared_task(base=LoggedTask)
def update_catalog_metadata_task(catalog_query_id):
    update_contentmetadata_from_discovery(catalog_query_id)
