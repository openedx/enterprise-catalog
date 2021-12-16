import copy
import functools
import json
import logging
from collections import defaultdict
from datetime import timedelta

from celery import shared_task, states
from celery.exceptions import Ignore
from celery_utils.logged_task import LoggedTask
from django.core.cache import cache
from django.db import IntegrityError
from django.db.models import Prefetch, Q
from django.db.utils import OperationalError
from django_celery_results.models import TaskResult
from requests.exceptions import ConnectionError as RequestsConnectionError

from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.algolia_utils import (
    ALGOLIA_FIELDS,
    ALGOLIA_UUID_BATCH_SIZE,
    configure_algolia_index,
    create_algolia_objects,
    get_algolia_object_id,
    get_initialized_algolia_client,
    partition_course_keys_for_indexing,
    partition_program_keys_for_indexing,
)
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    DISCOVERY_COURSE_KEY_BATCH_SIZE,
    DISCOVERY_PROGRAM_KEY_BATCH_SIZE,
    PROGRAM,
    TASK_BATCH_SIZE,
)
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    create_course_associated_programs,
    update_contentmetadata_from_discovery,
)
from enterprise_catalog.apps.catalog.utils import (
    batch,
    get_content_filter_hash,
    localized_utcnow,
)


logger = logging.getLogger(__name__)

ONE_HOUR = timedelta(hours=1)

UNREADY_TASK_RETRY_COUNTDOWN_SECONDS = 60 * 5

# ENT-4980 every batch "shard" record in Algolia should have all of these that pertain to the course
EXPLORE_CATALOG_TITLES = ['A la carte', 'Business', 'Education']


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


def _fetch_programs_by_keys(program_keys):
    """
    Fetches program data from discovery's /api/v1/programs endpoint for the provided program keys.

    Args:
        program_keys (list of str): Content keys for Program ContentMetadata objects.
    Returns:
        list of dict: Returns a list of dictionaries where each dictionary represents the program data from discovery.
    """
    programs = []
    discovery_client = DiscoveryApiClient()

    # Batch the program keys into smaller chunks so that we don't send too big of a request to discovery
    batched_program_keys = batch(program_keys, batch_size=DISCOVERY_PROGRAM_KEY_BATCH_SIZE)
    for program_keys_chunk in batched_program_keys:
        # Discovery expects the uuids param to be in the format ?uuids=program1,program2,...
        query_params = {'uuids': ','.join(program_keys_chunk)}
        programs.extend(discovery_client.get_programs(query_params=query_params))

    return programs


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
        task_args=json.dumps(task_object.request.args),
        task_kwargs=json.dumps(task_object.request.kwargs),
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

    If task is invoked with `force` kwarg, time since last run will be ignored.

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
            force = kwargs.get('force', False)
            delta = time_delta or ONE_HOUR
            if not force and task_recently_run(self, time_delta=delta):
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
        RequestsConnectionError,
        IntegrityError,
        OperationalError,
    )
    retry_kwargs = {'max_retries': 5}
    # Use exponential backoff for retrying tasks
    retry_backoff = True
    # Add randomness to backoff delays to prevent all tasks in queue from executing simultaneously
    retry_jitter = True


@shared_task(base=LoggedTaskWithRetry, bind=True, default_retry_delay=UNREADY_TASK_RETRY_COUNTDOWN_SECONDS)
@expiring_task_semaphore()
def update_full_content_metadata_task(self, force=False):  # pylint: disable=unused-argument
    """
    Looks up the full metadata from discovery's `/api/v1/courses` and `/api/v1/programs` endpoints to pad all
    ContentMetadata objects. The metadata is merged with the existing contents
    of the json_metadata field for each ContentMetadata record.

    Args:
        force (bool): If true, forces execution of task and ignores time since last run.
    """
    if unready_tasks(update_catalog_metadata_task, ONE_HOUR).exists():
        raise self.retry(
            exc=RequiredTaskUnreadyError(),
        )

    content_keys = [metadata.content_key for metadata in ContentMetadata.objects.filter(content_type=COURSE)]
    _update_full_content_metadata_course(content_keys)
    content_keys = [metadata.content_key for metadata in ContentMetadata.objects.filter(content_type=PROGRAM)]
    _update_full_content_metadata_program(content_keys)


def _update_full_content_metadata_course(content_keys):
    """
    Given content_keys, finds the associated ContentMetadata records with a type of course and looks up the full
    course metadata from discovery's /api/v1/courses endpoint to pad the ContentMetadata objects. The course
    metadata is merged with the existing contents of the json_metadata field for each ContentMetadata record.

    Args:
        content_keys (list of str): A list of content keys representing ContentMetadata objects that should have their
            metadata updated with the full Course metadata. This list gets filtered down to only those representing
            Course ContentMetadata objects.

    Returns:
        list of str: Returns the course keys that were updated and should be indexed in Algolia
            by the B2C logic. This is passed to the `index_enterprise_catalog_in_algolia_task` from
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

            metadata_record.json_metadata.update(course_metadata_dict)
            modified_content_metadata_records.append(metadata_record)
            program_content_keys = create_course_associated_programs(course_metadata_dict['programs'], metadata_record)
            _update_full_content_metadata_program(program_content_keys)

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
        partitioned_indexable_course_keys, __ = partition_course_keys_for_indexing(modified_content_metadata_records)
        indexable_course_keys.extend(partitioned_indexable_course_keys)

    logger.info(
        '{} total course keys were updated and are ready for indexing in Algolia'.format(len(indexable_course_keys))
    )


def _update_full_content_metadata_program(content_keys):
    """
    Given content_keys, finds the associated ContentMetadata records with a type of program and looks up the full
    program metadata from discovery's /api/v1/programs endpoint to pad the ContentMetadata objects. The program
    metadata is merged with the existing contents of the json_metadata field for each ContentMetadata record.

    Args:
        content_keys (list of str): A list of content keys representing ContentMetadata objects that should have their
            metadata updated with the full Program metadata. This list gets filtered down to only those representing
            Program ContentMetadata objects.

    Returns:
        list of str: Returns the program keys that were updated and should be indexed in Algolia
            by the B2C logic.
    """
    indexable_program_keys = []
    for content_keys_batch in batch(content_keys, batch_size=TASK_BATCH_SIZE):
        full_program_dicts = _fetch_programs_by_keys(content_keys_batch)
        if not full_program_dicts:
            logger.info('No programs were retrieved from course-discovery in this batch.')
            continue

        # Build a dictionary of the metadata that corresponds to the fetched keys to avoid a query for every course
        fetched_program_keys = [program['uuid'] for program in full_program_dicts]
        metadata_records_for_fetched_keys = ContentMetadata.objects.filter(
            content_key__in=fetched_program_keys,
        )
        metadata_by_key = {
            metadata.content_key: metadata
            for metadata in metadata_records_for_fetched_keys
        }

        # Iterate through the programs to update the json_metadata field,
        # merging the minimal json_metadata retrieved by
        # `/search/all/` with the full json_metadata retrieved by `/programs/`.
        modified_content_metadata_records = []
        for program_metadata_dict in full_program_dicts:
            content_key = program_metadata_dict.get('uuid')
            metadata_record = metadata_by_key.get(content_key)
            if not metadata_record:
                logger.error('Could not find ContentMetadata record for content_key %s.', content_key)
                continue

            metadata_record.json_metadata.update(program_metadata_dict)
            modified_content_metadata_records.append(metadata_record)

        ContentMetadata.objects.bulk_update(
            modified_content_metadata_records,
            ['json_metadata'],
            batch_size=10,
        )

        logger.info(
            'Successfully updated %d of %d ContentMetadata records with full metadata from course-discovery.',
            len(modified_content_metadata_records),
            len(full_program_dicts),
        )

        # record the program uuids that were updated and should be indexed in Algolia by the B2C logic
        partitioned_indexable_program_keys, __ = partition_program_keys_for_indexing(modified_content_metadata_records)
        indexable_program_keys.extend(partitioned_indexable_program_keys)

    logger.info(
        '{} total program keys were updated and are ready for indexing in Algolia'.format(len(indexable_program_keys))
    )


def _add_in_algolia_products_by_object_id(algolia_products_by_object_id, batched_metadata):
    """
    Adds batched_metadata in algolia_products_by_object_id dict.

    There can be possible duplicate products due to course associated programs coming in different batches.
    We are added metadata in products by objectId here to remove duplicate data.
    """
    for metadata in batched_metadata:
        algolia_products_by_object_id[metadata['objectID']] = metadata


def _batched_metadata(json_metadata, sorted_uuids, uuid_key_name, obj_id_fmt):
    batched_metadata = []
    for batch_index, uuid_batch in enumerate(batch(sorted_uuids, batch_size=ALGOLIA_UUID_BATCH_SIZE)):
        json_metadata_with_uuids = copy.deepcopy(json_metadata)
        json_metadata_with_uuids.update({
            'objectID': obj_id_fmt.format(json_metadata['objectID'], batch_index),
            uuid_key_name: uuid_batch,
        })
        batched_metadata.append(json_metadata_with_uuids)
    return batched_metadata


def _batched_metadata_with_queries(json_metadata, sorted_queries):
    """
    Batched catalog queries are represented as tuples (<query uuid>, <query title>). Unzip the two fields and update
    them together.
    """

    # ENT-4980 every batch "shard" record in Algolia should have all of these that pertain to the course
    course_catalog_query_titles = list(map(lambda x: x[1], sorted_queries))
    explore_catalog_membership = list(filter(lambda y: y in EXPLORE_CATALOG_TITLES, course_catalog_query_titles))
    batched_metadata = []
    for batch_index, query_batch in enumerate(batch(sorted_queries, batch_size=ALGOLIA_UUID_BATCH_SIZE)):
        json_metadata_with_uuids = copy.deepcopy(json_metadata)

        query_uuids, query_titles = list(map(list, zip(*query_batch)))
        # filter out `None` from `query_titles`, join with explore titles, dedupe (set), sort
        batch_titles = sorted(set([title for title in query_titles if title] + explore_catalog_membership))
        metadata_to_update = {
            'objectID': f"{json_metadata['objectID']}-catalog-query-uuids-{batch_index}",
            'enterprise_catalog_query_uuids': sorted(query_uuids),
            'enterprise_catalog_query_titles': batch_titles,
        }
        json_metadata_with_uuids.update(metadata_to_update)
        batched_metadata.append(json_metadata_with_uuids)
    return batched_metadata


@shared_task(base=LoggedTaskWithRetry, bind=True, default_retry_delay=UNREADY_TASK_RETRY_COUNTDOWN_SECONDS)
@expiring_task_semaphore()
def index_enterprise_catalog_in_algolia_task(self, force=False):  # pylint: disable=unused-argument
    """
    Index course and program data in Algolia with enterprise-related fields.

    Note: It is especially important that this task uses the increased maximum ``CELERY_TASK_SOFT_TIME_LIMIT`` and
    ``CELERY_TASK_TIME_LIMIT`` as it makes somewhat time-intensive reads/writes to the database along with sending
    large payloads of data to Algolia, which was exceeding the previous default limits, causing a SoftTimeLimitExceeded
    exception.

    Args:
        force (bool): If true, forces execution of task and ignores time since last run.
    """
    try:
        if unready_tasks(update_full_content_metadata_task, ONE_HOUR).exists():
            raise self.retry(
                exc=RequiredTaskUnreadyError(),
            )
        courses_content_metadata = ContentMetadata.objects.filter(content_type=COURSE)
        indexable_course_keys, nonindexable_course_keys = partition_course_keys_for_indexing(
            courses_content_metadata,
        )
        programs_content_metadata = ContentMetadata.objects.filter(content_type=PROGRAM)
        indexable_program_keys, nonindexable_program_keys = partition_program_keys_for_indexing(
            programs_content_metadata,
        )
        indexable_content_keys = indexable_course_keys + indexable_program_keys
        nonindexable_content_keys = nonindexable_course_keys + nonindexable_program_keys
        _reindex_algolia(
            indexable_content_keys=indexable_content_keys,
            nonindexable_content_keys=nonindexable_content_keys,
        )
    except Exception as exep:
        logger.exception(f'[ENTERPRISE_CATALOG_ALGOLIA_REINDEX] reindex_algolia failed. Error: {exep}')
        raise exep


def index_content_keys_in_algolia(content_keys, algolia_client):  # pylint: disable=too-many-statements
    """
    Determines list of Algolia objects to include in the Algolia index based on the
    specified content keys, and replaces all existing objects with the new ones in an atomic reindex.

    Arguments:
        content_keys (list): List of indexable content_key strings.
        algolia_client: Instance of an Algolia API client
    """
    logger.info(
        f'[ENTERPRISE_CATALOG_ALGOLIA_REINDEX] There are {len(content_keys)} total content keys to include in the'
        f' Algolia index.'
    )
    algolia_products_by_object_id = {}
    batch_num = 1
    catalog_uuids_by_key = defaultdict(set)
    customer_uuids_by_key = defaultdict(set)
    catalog_queries_by_key = defaultdict(set)
    for content_keys_batch in batch(content_keys, batch_size=TASK_BATCH_SIZE):
        # retrieve ContentMetadata records that match the specified content_keys in the
        # content_key or parent_content_key or course associated programs. returns courses, programs and course runs.
        query = (
            Q(content_key__in=content_keys_batch)
            | Q(parent_content_key__in=content_keys_batch)
            | Q(associated_content_metadata__content_key__in=content_keys_batch, content_type=PROGRAM)
        )

        catalog_queries = CatalogQuery.objects.prefetch_related(
            'enterprise_catalogs',
        )
        associate_programs_query = ContentMetadata.objects.filter(content_type=PROGRAM)
        content_metadata = ContentMetadata.objects.filter(query).prefetch_related(
            Prefetch('catalog_query_mapping', queryset=catalog_queries),
            Prefetch('associated_content_metadata', queryset=associate_programs_query, to_attr='associate_programs'),
        )
        logger.info(
            f'[ENTERPRISE_CATALOG_ALGOLIA_REINDEX] batch#{batch_num}: {content_metadata.count()} metadata found.'
        )

        # iterate through ContentMetadata records, retrieving the enterprise_catalog_uuids
        # and enterprise_customer_uuids associated with each ContentMetadata record (either
        # a course or a course run or program), storing them in a dictionary with the related
        # content_key as a key for later retrieval. the content_key is determined by
        # the content_key field if the metadata is a `COURSE` or `PROGRAM` or by the parent_content_key
        # field if the metadata is a `COURSE_RUN`.
        for metadata in content_metadata:
            if metadata.content_type in (COURSE, PROGRAM):
                content_key = metadata.content_key
            else:
                content_key = metadata.parent_content_key
            associated_queries = metadata.catalog_query_mapping.all()
            enterprise_catalog_uuids = set()
            enterprise_customer_uuids = set()
            enterprise_catalog_queries = set()
            for query in associated_queries:
                enterprise_catalog_queries.add((str(query.uuid), query.title))
                associated_catalogs = query.enterprise_catalogs.all()
                for catalog in associated_catalogs:
                    enterprise_catalog_uuids.add(str(catalog.uuid))
                    enterprise_customer_uuids.add(str(catalog.enterprise_uuid))

            # add to any existing enterprise catalog uuids, enterprise customer uuids or catalog query uuids
            catalog_uuids_by_key[content_key].update(enterprise_catalog_uuids)
            customer_uuids_by_key[content_key].update(enterprise_customer_uuids)
            catalog_queries_by_key[content_key].update(enterprise_catalog_queries)

            if metadata.content_type == COURSE:
                # course metadata might have associated programs. add them as well.
                for program_metadata in metadata.associate_programs:
                    content_key = program_metadata.content_key
                    catalog_uuids_by_key[content_key].update(enterprise_catalog_uuids)
                    customer_uuids_by_key[content_key].update(enterprise_customer_uuids)
                    catalog_queries_by_key[content_key].update(enterprise_catalog_queries)

        # iterate through the courses and programs, retrieving the enterprise-related uuids from the
        # dictionary created above. there is at least 2 duplicate course records per course,
        # each including the catalog uuids and customer uuids respectively.
        #
        # if the number of uuids for both catalogs/customers exceeds ALGOLIA_UUID_BATCH_SIZE, then
        # create duplicate course records, batching the uuids (flattened records) to reduce
        # the payload size of the Algolia objects.
        filtered_content_metadata = content_metadata.filter(Q(content_type=COURSE) | Q(content_type=PROGRAM))
        for metadata in filtered_content_metadata:
            content_key = metadata.content_key

            # We need to process PROGRAMS everytime as course associated programs can come in multiple batches.
            if _was_recently_indexed(content_key) and not metadata.content_type == PROGRAM:
                continue

            # add enterprise-related uuids to json_metadata
            json_metadata = copy.deepcopy(metadata.json_metadata)
            json_metadata.update({
                'objectID': get_algolia_object_id(json_metadata.get('content_type'), json_metadata.get('uuid')),
            })

            # enterprise catalog uuids
            catalog_uuids = sorted(list(catalog_uuids_by_key[content_key]))
            batched_metadata = _batched_metadata(
                json_metadata,
                catalog_uuids,
                'enterprise_catalog_uuids',
                '{}-catalog-uuids-{}',
            )
            _add_in_algolia_products_by_object_id(algolia_products_by_object_id, batched_metadata)

            # enterprise customer uuids
            customer_uuids = sorted(list(customer_uuids_by_key[content_key]))
            batched_metadata = _batched_metadata(
                json_metadata,
                customer_uuids,
                'enterprise_customer_uuids',
                '{}-customer-uuids-{}',
            )
            _add_in_algolia_products_by_object_id(algolia_products_by_object_id, batched_metadata)
            _mark_recently_indexed(content_key)

            # enterprise catalog queries (tuples of (query uuid, query title)), note: account for None being present
            # within the list
            queries = sorted(list(catalog_queries_by_key[content_key]))
            batched_metadata = _batched_metadata_with_queries(json_metadata, queries)
            _add_in_algolia_products_by_object_id(algolia_products_by_object_id, batched_metadata)
        batch_num += 1

    logger.info(
        f'[ENTERPRISE_CATALOG_ALGOLIA_REINDEX] {len(algolia_products_by_object_id.keys())} products found.'
    )

    # extract out only the fields we care about and send to Algolia index
    algolia_objects = create_algolia_objects(algolia_products_by_object_id.values(), ALGOLIA_FIELDS)
    algolia_client.replace_all_objects(algolia_objects)


def _reindex_algolia(indexable_content_keys, nonindexable_content_keys):
    """
    Indexes courses and programs metadata in the Algolia search index.
    """
    # NOTE: this log message is used in a Splunk alert and should remain consistent in its language
    logger.info(
        '[ENTERPRISE_CATALOG_ALGOLIA_REINDEX] There are %s indexable content keys, which will replace all existing'
        ' objects in the Algolia index. %s nonindexable content keys will be removed.',
        len(indexable_content_keys), len(nonindexable_content_keys),
    )
    if len(indexable_content_keys) == 0:
        logger.warning('Skipping Algolia indexing as there are no indexable content keys.')
        # ensure we do not continue the indexing task if there are no indexable content keys. this
        # will help prevent us from unintentionally removing all content keys from the index.
        return

    algolia_client = get_initialized_algolia_client()
    configure_algolia_index(algolia_client)

    # Replaces all objects in the Algolia index with new objects based on the specified
    # indexable content keys.
    index_content_keys_in_algolia(
        content_keys=indexable_content_keys,
        algolia_client=algolia_client,
    )


def _was_recently_indexed(content_key):
    """
    Helper to determine if the given ``content_key`` was recently marked
    as having been updated in the Algolia index.
    """
    cache_key = _algolia_recent_update_cache_key(content_key)
    return cache.get(cache_key, False)


def _mark_recently_indexed(content_key):
    """
    Helper to mark the given ``content_key`` as having recently
    been updated in the Algolia index.  Expires after 30 minutes.
    This is useful because multiple metadata records of type COURSE_RUN
    might point to a single metadata record of type COURSE, and by marking
    a course record as recently indexed in one batch, we can avoid
    updating it in subsequent batches.
    """
    cache_key = _algolia_recent_update_cache_key(content_key)
    cache.set(cache_key, True, 60 * 30)


def _algolia_recent_update_cache_key(content_key):
    """
    Helper that returns a cache key for the given content key
    indicating that the content_key was recently updated in the Algolia index.
    """
    # TODO: Replacing spaces with underscores because we have some bad content keys
    # floating around.  Ideally, there would be better data validation upstream
    # AND we would clean up these keys across our systems.
    # Memcached does NOT like spaces in its keys.
    return 'algolia-recent-update-{}'.format(content_key.replace(' ', '_'))


@shared_task(base=LoggedTaskWithRetry, bind=True)
@expiring_task_semaphore()
def update_catalog_metadata_task(self, catalog_query_id, force=False):  # pylint: disable=unused-argument
    """
    Associates ContentMetadata objects with the appropriate catalog query by pulling data
    from /search/all on discovery.

    Args:
        catalog_query_id (str): The id for the catalog query to update.
        force (bool): If true, forces execution of task and ignores time since last run.
    Returns:
        list of str: Returns the content keys for ContentMetadata objects that were associated with the query.
            This result can be passed to the `update_full_content_metadata_task`.
    """
    try:
        catalog_query = CatalogQuery.objects.get(id=catalog_query_id)
    except CatalogQuery.DoesNotExist:
        logger.error('Could not find a CatalogQuery with id %s', catalog_query_id)

    associated_content_keys = update_contentmetadata_from_discovery(catalog_query)
    logger.info('Finished update_catalog_metadata_task with {} associated content keys for catalog {}'.format(
        len(associated_content_keys), catalog_query_id
    ))


@shared_task(base=LoggedTaskWithRetry, bind=True)
@expiring_task_semaphore()
def fetch_missing_course_metadata_task(self):  # pylint: disable=unused-argument
    """
    Creates a CatalogQuery for all the courses that do not have ContentMetadata instance.

    After creating the catalog query it calls update_contentmetadata_from_discovery to update the metadata for these
    courses. Course metadata is only missing for program courses so the initial query only looks for course metadata
    that are embedded inside a program.
    """

    program_metadata_list = ContentMetadata.objects.filter(content_type=PROGRAM).values_list('json_metadata', flat=True)
    course_keys = set()
    for program_metadata in program_metadata_list:
        if program_metadata is not None:
            course_keys.update([item.get('key') for item in program_metadata.get('courses', [])])

    # Check which courses do not have content metadata.
    present_course_keys = ContentMetadata.objects.filter(
        content_type=COURSE, content_key__in=course_keys
    ).values_list(
        'content_key', flat=True
    )

    missing_course_keys = course_keys.difference(present_course_keys)
    content_filter = {
        'status': 'published',
        'key': list(missing_course_keys),
        'content_type': 'course',
    }

    catalog_query, _ = CatalogQuery.objects.get_or_create(
        content_filter_hash=get_content_filter_hash(content_filter),
        defaults={'content_filter': content_filter, 'title': None},
    )

    associated_content_keys = update_contentmetadata_from_discovery(catalog_query)
    logger.info('Finished fetch_missing_course_metadata_task with {} associated content keys for catalog {}'.format(
        len(associated_content_keys), catalog_query.id
    ))
