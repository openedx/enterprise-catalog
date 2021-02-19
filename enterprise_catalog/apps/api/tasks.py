import copy
import functools
import logging
from collections import defaultdict
from datetime import timedelta

from celery import shared_task, states
from celery.exceptions import Ignore, SoftTimeLimitExceeded
from celery.exceptions import TimeoutError as CeleryTimeoutError
from celery_utils.logged_task import LoggedTask
from django.conf import settings
from django.db import IntegrityError
from django.db.models import Prefetch, Q
from django.db.utils import OperationalError
from django.utils import timezone
from django_celery_results.models import TaskResult

from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.algolia_utils import (
    ALGOLIA_UUID_BATCH_SIZE,
    create_algolia_objects_from_courses,
    get_algolia_object_id,
    get_indexable_course_keys,
    get_initialized_algolia_client,
)
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    DISCOVERY_COURSE_KEY_BATCH_SIZE,
    TASK_BATCH_SIZE,
)
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    update_contentmetadata_from_discovery,
)
from enterprise_catalog.apps.catalog.utils import batch, localized_utcnow


logger = logging.getLogger(__name__)


def _get_course_keys_for_updating(content_keys_for_updating):
    """
    Gets the list of keys of course ContentMetadata objects that need to be updated.

    Args:
        content_keys_for_updating (list of str): Content keys for ContentMetadata objects that are to be updated.
    Returns:
        list of str: Returns the list of keys that represent courses from the provided `content_keys_for_updating`.
    """
    related_course_content_metadata = ContentMetadata.objects.filter(
        content_key__in=content_keys_for_updating,
        content_type=COURSE,
    )
    return [metadata.content_key for metadata in related_course_content_metadata]


def _fetch_courses_by_keys(course_keys):
    """
    Fetches course data from discovery's /api/v1/courses endpoint for the provided course keys.

    Args:
        course_keys (list of str): Content keys for Course ContentMetadata objects.
    Returns:
        list of dict: Returns a list of dictionaries where each dictionary represents the course data from discovery.
    """
    courses = []
    course_keys_to_fetch = []
    discovery_client = DiscoveryApiClient()
    timeout_seconds = settings.DISCOVERY_COURSE_DATA_CACHE_TIMEOUT

    # Populate a new list of course keys that haven't been updated recently to request from the Discovery API.
    for key in course_keys:
        content_metadata = ContentMetadata.objects.filter(content_key=key)
        if not content_metadata:
            continue
        if timezone.now() - content_metadata[0].modified > timedelta(seconds=timeout_seconds):
            courses.append(content_metadata[0].json_metadata)
        else:
            course_keys_to_fetch.append(key)

    # Batch the course keys into smaller chunks so that we don't send too big of a request to discovery
    batched_course_keys = batch(course_keys_to_fetch, batch_size=DISCOVERY_COURSE_KEY_BATCH_SIZE)
    for course_keys_chunk in batched_course_keys:
        # Discovery expects the keys param to be in the format ?keys=course1,course2,...
        query_params = {'keys': ','.join(course_keys_chunk)}
        courses.extend(discovery_client.get_courses(query_params=query_params))

    return courses


def task_recently_run(task_object, time_delta):
    """
    Given a celery Task, queries the `TaskResult` model to determine
    if a task with the same (name, args, kwargs) was created
    within the given (`time_delta`, now) range.

    Args:
      task_object (Task): A celery task object.
      time_delta (timedelta): A timedelta.
    Returns:
      Boolean: Whether an equivalent task with the same (name, args, kwargs) recently existed
      in a non-failure or non-revoked state.
    """
    return TaskResult.objects.filter(
        task_name=task_object.name,
        task_args=str(task_object.request.args),
        task_kwargs=str(task_object.request.kwargs),
        date_created__gte=localized_utcnow() - time_delta,
    ).exclude(
        status__in=(states.FAILURE, states.REVOKED),
    ).exclude(
        task_id=str(task_object.request.id),
    ).exists()


class TaskRecentlyRunError(Ignore):
    """
    An exception representing a state where a given task with the same name/args
    has recently been executed in a non-failing, non-revoked state.
    """


def expiring_task_semaphore(time_delta=None):
    """
    Celery Task decorator that wraps a bound (bind=True) task.
    If another task with the same (name, args, kwargs) as the given task
    was executed in the time between `time_delta` and now, the task moves to a REVOKED
    state and raises a `TaskRecentlyRunError`.

    The `meta` state of the task is updated
    with `exc_type` and `exc_info`; otherwise, any process that's watching for the result
    of the task (e.g. via `task.get()`) and finds that it results in a failed state
    (REVOKED counts as a failed state) will attempt to re-raise a captured exception,
    which would not exist without populating these two exc fields.

    `time_delta` defaults to one hour.

    Args:
      time_delta (datetime.timedelta): An optional timedelta that specifies how far back
        to look for the same task.
    """
    def decorator(task):
        @functools.wraps(task)
        def wrapped_task(self, *args, **kwargs):
            delta = time_delta or timedelta(hours=1)
            if task_recently_run(self, time_delta=delta):
                msg_args = (self.name, self.request.id, self.request.args, self.request.kwargs)
                message = (
                    '{} task with id {} was recently run with '
                    'args: {} kwargs: {}, task returning without updating.'
                ).format(*msg_args)
                logger.info(message)
                self.update_state(
                    state=states.REVOKED,
                    meta={
                        'exc_type': TaskRecentlyRunError.__name__,
                        'exc_message': message,
                    },
                )
                raise TaskRecentlyRunError(message)
            return task(self, *args, *kwargs)
        return wrapped_task
    return decorator


class LoggedTaskWithRetry(LoggedTask):  # pylint: disable=abstract-method
    """
    Shared base task that allows tasks that raise some common exceptions to retry automatically.

    See https://docs.celeryproject.org/en/stable/userguide/tasks.html#automatic-retry-for-known-exceptions for
    more documentation.
    """
    autoretry_for = (
        IntegrityError,
        SoftTimeLimitExceeded,
        CeleryTimeoutError,
        OperationalError,
    )
    retry_kwargs = {'max_retries': 5}
    # Use exponential backoff for retrying tasks
    retry_backoff = True
    # Add randomness to backoff delays to prevent all tasks in queue from executing simultaneously
    retry_jitter = True


@shared_task(base=LoggedTaskWithRetry)
def update_full_content_metadata_task(content_keys):
    """
    Given content_keys, finds the associated ContentMetadata records with a type of course and looks up the full
    course metadata from discovery's /api/v1/cousres endpoint to pad the ContentMetadata objects with. The course
    metadata is merged with the existing contents of the json_metadata field for each ContentMetadata record.

    Note: It is especially important that this task uses the increased maximum ``CELERY_TASK_SOFT_TIME_LIMIT`` and
    ``CELERY_TASK_TIME_LIMIT`` since the task traverses large portions of course-discovery's /courses/ endpoint, which
    was exceeding the previous default limits, causing a SoftTimeLimitExceeded exception.

    Args:
        content_keys (list of str): A list of content keys representing ContentMetadata objects that should have their
            metadata updated with the full Course metadata. This list gets filtered down to only those representing
            Course ContentMetadata objects.

    Returns:
        list of str: Returns the course keys that were updated and should be indexed in Algolia
            by the B2C logic. This is passed to the `index_enterprise_catalog_courses_in_algolia_task` from
            the `EnterpriseCatalogRefreshDataFromDiscovery` view.
    """
    indexable_course_keys = []
    for content_keys_batch in batch(content_keys, batch_size=TASK_BATCH_SIZE):
        course_keys_for_updating = _get_course_keys_for_updating(content_keys_batch)

        courses = _fetch_courses_by_keys(course_keys_for_updating)
        if not courses:
            logger.info('No courses were retrieved from course-discovery in this batch.')
            continue
        logger.info('Retrieved %d courses from course-discovery in this batch.', len(courses))

        # Iterate through the courses to update the json_metadata field, merging the minimal json_metadata retrieved by
        # /search/all/ with the full json_metadata retrieved by /courses/.
        fetched_course_keys = [course['key'] for course in courses]
        metadata_for_fetched_keys = ContentMetadata.objects.filter(content_key__in=fetched_course_keys)
        # Build a dictionary of the metadata that corresponds to the fetched keys to avoid a query for every course
        metadata_by_key = {metadata.content_key: metadata for metadata in metadata_for_fetched_keys}
        updated_metadata = []
        for course_metadata in courses:
            content_key = course_metadata.get('key')
            metadata_record = metadata_by_key.get(content_key)
            if not metadata_by_key:
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
            len(courses),
        )

        # record the course keys that were updated and should be indexed in Algolia by the B2C logic
        indexable_course_keys.extend(get_indexable_course_keys(updated_metadata))

    logger.info(
        '{} total course keys were updated and are ready for indexing in Algolia'.format(len(indexable_course_keys))
    )
    return indexable_course_keys


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


@shared_task(base=LoggedTaskWithRetry)
def index_enterprise_catalog_courses_in_algolia_task(
    content_keys,
    algolia_fields,
    uuid_batch_size=ALGOLIA_UUID_BATCH_SIZE,
):
    """
    Index course data in Algolia with enterprise-related fields.

    Note: It is especially important that this task uses the increased maximum ``CELERY_TASK_SOFT_TIME_LIMIT`` and
    ``CELERY_TASK_TIME_LIMIT`` as it makes somewhat time-intensive reads/writes to the database along with sending
    large payloads of data to Algolia, which was exceeding the previous default limits, causing a SoftTimeLimitExceeded
    exception.

    Arguments:
        content_keys (list): A list of content_keys.  It's important that this is the first positional argument,
            so that the passing of return values to the signature of the next chained celery task
            works as expected.
        algolia_fields (list): A list of course fields we want to index in Algolia
        uuid_batch_size (int): The threshold of distinct catalog/customer UUIDs associated with a piece of content,
            at which duplicate course records are created in the index,
            batching the uuids (flattened records) to reduce the payload size of the Algolia objects.
            Defaults to ``ALGOLIA_UUID_BATCH_SIZE``.
    """
    algolia_client = get_initialized_algolia_client()

    if not algolia_fields or not content_keys:
        logger.error('Must provide algolia_fields and content_keys as arguments.')
        return

    # Update the index in batches
    for content_keys_batch in batch(content_keys, batch_size=TASK_BATCH_SIZE):
        courses = []
        catalog_uuids_by_course_key = defaultdict(set)
        customer_uuids_by_course_key = defaultdict(set)

        # retrieve ContentMetadata records that match the specified content_keys in the
        # content_key or parent_content_key. returns both courses and course runs.
        query = Q(content_key__in=content_keys_batch) | Q(parent_content_key__in=content_keys_batch)

        catalog_queries = CatalogQuery.objects.prefetch_related(
            'enterprise_catalogs',
        )
        content_metadata = ContentMetadata.objects.filter(query).prefetch_related(
            Prefetch('catalog_queries', queryset=catalog_queries),
        )

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
                associated_catalogs = query.enterprise_catalogs.all()
                for catalog in associated_catalogs:
                    enterprise_catalog_uuids.add(str(catalog.uuid))
                    enterprise_customer_uuids.add(str(catalog.enterprise_uuid))

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


@shared_task(base=LoggedTaskWithRetry, bind=True)
@expiring_task_semaphore()
def update_catalog_metadata_task(self, catalog_query_id):  # pylint: disable=unused-argument
    """
    Updates all ContentMetadata associated with the catalog query by pulling in data from /search/all on discovery

    Args:
        catalog_query_id (str): The id for the catalog query to update.
    Returns:
        list of str: Returns the content keys for ContentMetadata objects that were associated with the query.
            This result can be passed to the `update_full_content_metadata_task`.
    """
    try:
        catalog_query = CatalogQuery.objects.get(id=catalog_query_id)
    except CatalogQuery.DoesNotExist:
        logger.error('Could not find a CatalogQuery with id %s', catalog_query_id)
        return []

    associated_content_keys = update_contentmetadata_from_discovery(catalog_query)
    logger.info('Finished update_catalog_metadata_task with {} associated content keys for catalog {}'.format(
        len(associated_content_keys), catalog_query_id
    ))
    return associated_content_keys
