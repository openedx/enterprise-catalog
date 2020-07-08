import copy
import logging
from collections import defaultdict

from celery import shared_task
from celery_utils.logged_task import LoggedTask
from django.db.models import Q

from enterprise_catalog.apps.api.v1.utils import (
    create_algolia_objects_from_courses,
    get_algolia_object_id,
)
from enterprise_catalog.apps.api_client.algolia import AlgoliaSearchClient
from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.constants import (
    ALGOLIA_UUID_BATCH_SIZE,
    COURSE,
)
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    content_metadata_with_type_course,
    update_contentmetadata_from_discovery,
)
from enterprise_catalog.apps.catalog.utils import batch


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


def _batched_metadata(json_metadata, sorted_uuids, uuid_key_name, obj_id_fmt, uuid_batch_size):
    batched_metadata = []
    for batch_index, uuid_batch in enumerate(batch(sorted_uuids, batch_size=uuid_batch_size)):
        json_metadata_with_uuids = copy.deepcopy(json_metadata)
        json_metadata_with_uuids.update({
            'objectID': obj_id_fmt.format(json_metadata['objectID'], batch_index),
            uuid_key_name: uuid_batch,
        })
        batched_metadata.append(json_metadata_with_uuids)
    return batched_metadata


@shared_task(base=LoggedTask)
def index_enterprise_catalog_courses_in_algolia_task(
    algolia_fields, content_keys, uuid_batch_size=ALGOLIA_UUID_BATCH_SIZE
):
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
    catalog_uuids_by_course_key = defaultdict(set)
    customer_uuids_by_course_key = defaultdict(set)

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

        # add to any existing enterprise catalog uuids or enterprise customer uuids
        catalog_uuids_by_course_key[course_content_key].update(enterprise_catalog_uuids)
        customer_uuids_by_course_key[course_content_key].update(enterprise_customer_uuids)

    # iterate through only the courses, retrieving the enterprise-related uuids from the
    # dictionary created above. there is at least 2 duplicate course records per course,
    # each including the catalog uuids and customer uuids respectively.
    #
    # if the number of uuids for both catalogs/customers exceeds uuid_batch_size, then
    # create duplicate course records, batching the uuids (flattened records) to reduce
    # the payload size of the Algolia objects.
    course_content_metadata = content_metadata.filter(content_type=COURSE)
    for metadata in course_content_metadata:
        content_key = metadata.content_key
        # add enterprise-related uuids to json_metadata
        json_metadata = copy.deepcopy(metadata.json_metadata)
        json_metadata.update({
            'objectID': get_algolia_object_id(json_metadata.get('uuid')),
        })

        # enterprise catalog uuids
        catalog_uuids = sorted(list(catalog_uuids_by_course_key[content_key]))
        batched_metadata = _batched_metadata(
            json_metadata,
            catalog_uuids,
            'enterprise_catalog_uuids',
            '{}-catalog-uuids-{}',
            uuid_batch_size,
        )
        courses.extend(batched_metadata)

        # enterprise customer uuids
        customer_uuids = sorted(list(customer_uuids_by_course_key[content_key]))
        batched_metadata = _batched_metadata(
            json_metadata,
            customer_uuids,
            'enterprise_customer_uuids',
            '{}-customer-uuids-{}',
            uuid_batch_size,
        )
        courses.extend(batched_metadata)

    # extract out only the fields we care about and send to Algolia index
    algolia_objects = create_algolia_objects_from_courses(courses, algolia_fields)
    algolia_client.partially_update_index(algolia_objects)


@shared_task(base=LoggedTask)
def update_catalog_metadata_task(catalog_query_id):
    update_contentmetadata_from_discovery(catalog_query_id)
