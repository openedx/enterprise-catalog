import copy
import functools
import logging
from collections import defaultdict
from datetime import timedelta

from celery import shared_task, states
from celery.exceptions import Ignore, SoftTimeLimitExceeded
from celery.exceptions import TimeoutError as CeleryTimeoutError
from celery_utils.logged_task import LoggedTask
from django.db import IntegrityError
from django.db.models import Prefetch, Q
from django.db.utils import OperationalError
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

UNREADY_TASK_RETRY_COUNTDOWN_SECONDS = 60 * 5


def _fetch_courses_by_keys(course_keys):
    """
    Fetches course data from discovery's /api/v1/courses endpoint for the provided course keys.

    Args:
        course_keys (list of str): Content keys for Course ContentMetadata objects.
    Returns:
        list of dict: Returns a list of dictionaries where each dictionary represents the course data from discovery.
    """
    courses = []
    discovery_client = DiscoveryApiClient()

    # Batch the course keys into smaller chunks so that we don't send too big of a request to discovery
    batched_course_keys = batch(course_keys, batch_size=DISCOVERY_COURSE_KEY_BATCH_SIZE)
    for course_keys_chunk in batched_course_keys:
        # Discovery expects the keys param to be in the format ?keys=course1,course2,...
        query_params = {'keys': ','.join(course_keys_chunk)}
        courses.extend(discovery_client.get_courses(query_params=query_params))

    return courses


def unready_tasks(celery_task, time_delta):
    """
    Returns any unready tasks with the name of the given celery task
    that were created within the given (now - time_delta, now) range.
    The unready celery states are
    {'RECEIVED', 'REJECTED', 'STARTED', 'PENDING', 'RETRY'}.
    https://docs.celeryproject.org/en/v5.0.5/reference/celery.states.html#unready-states

    Args:
      celery_task: A celery task definition or "type" (not an applied task "instance"),
        for example, ``update_catalog_metadata_task``.
      time_delta: A datetime.timedelta indicating how for back to look for unready tasks of this type.
    """
    return TaskResult.objects.filter(
        task_name=celery_task.name,
        date_created__gte=localized_utcnow() - time_delta,
        status__in=states.UNREADY_STATES,
    )


def task_recently_run(task_object, time_delta):
    """
    Given a celery Task, queries the `TaskResult` model to determine
    if a task with the same (name, args, kwargs) was created
    within the given (now - time_delta, now) range.

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


class RequiredTaskUnreadyError(Exception):
    """
    An exception representing a state where one type of task that is required
    to be complete before another task is run is not in a ready state.
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


@shared_task(base=LoggedTaskWithRetry, bind=True, default_retry_delay=UNREADY_TASK_RETRY_COUNTDOWN_SECONDS)
@expiring_task_semaphore()
def update_full_content_metadata_task(self):
    """
    Looks up the full course metadata from discovery's `/api/v1/courses` endpoint to pad all
    ContentMetadata objects with, so long as the record was modified within the last hour.
    The course metadata is merged with the existing contents
    of the json_metadata field for each ContentMetadata record.

    Note: It is especially important that this task uses the increased maximum ``CELERY_TASK_SOFT_TIME_LIMIT`` and
    ``CELERY_TASK_TIME_LIMIT`` since the task traverses large portions of course-discovery's /courses/ endpoint, which
    was exceeding the previous default limits, causing a SoftTimeLimitExceeded exception.
    """
    content_keys = [
        metadata.content_key for metadata in
        ContentMetadata.recently_modified_records(timedelta(hours=1)).filter(content_type=COURSE)
    ]
    if unready_tasks(update_catalog_metadata_task, timedelta(hours=1)).exists():
        raise self.retry(
            exc=RequiredTaskUnreadyError(),
        )

    return _update_full_content_metadata(content_keys)


def _update_full_content_metadata(content_keys):
    """
    Given content_keys, finds the associated ContentMetadata records with a type of course and looks up the full
    course metadata from discovery's /api/v1/cousres endpoint to pad the ContentMetadata objects with. The course
    metadata is merged with the existing contents of the json_metadata field for each ContentMetadata record.

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
        full_course_dicts = _fetch_courses_by_keys(content_keys_batch)
        if not full_course_dicts:
            logger.info('No courses were retrieved from course-discovery in this batch.')
            continue

        # Build a dictionary of the metadata that corresponds to the fetched keys to avoid a query for every course
        fetched_course_keys = [course['key'] for course in full_course_dicts]
        metadata_records_for_fetched_keys = ContentMetadata.objects.filter(
            content_key__in=fetched_course_keys,
        )
        metadata_by_key = {
            metadata.content_key: metadata
            for metadata in metadata_records_for_fetched_keys
        }

        # Iterate through the courses to update the json_metadata field,
        # merging the minimal json_metadata retrieved by
        # `/search/all/` with the full json_metadata retrieved by `/courses/`.
        modified_content_metadata_records = []
        for course_metadata_dict in full_course_dicts:
            content_key = course_metadata_dict.get('key')
            metadata_record = metadata_by_key.get(content_key)
            if not metadata_record:
                logger.error('Could not find ContentMetadata record for content_key %s.', content_key)
                continue

            metadata_record.merge_json_metadata(course_metadata_dict)
            modified_content_metadata_records.append(metadata_record)

        ContentMetadata.objects.bulk_update(
            modified_content_metadata_records,
            ['json_metadata'],
            batch_size=10,
        )

        logger.info(
            'Successfully updated %d of %d ContentMetadata records with full metadata from course-discovery.',
            len(modified_content_metadata_records),
            len(full_course_dicts),
        )

        # record the course keys that were updated and should be indexed in Algolia by the B2C logic
        indexable_course_keys.extend(get_indexable_course_keys(modified_content_metadata_records))

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
