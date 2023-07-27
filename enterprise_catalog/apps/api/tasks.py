import copy
import functools
import json
import logging
import time
from collections import defaultdict
from datetime import timedelta
from operator import itemgetter

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
    _get_course_run_by_uuid,
    configure_algolia_index,
    create_algolia_objects,
    get_algolia_object_id,
    get_initialized_algolia_client,
    get_pathway_course_keys,
    get_pathway_program_uuids,
    partition_course_keys_for_indexing,
    partition_program_keys_for_indexing,
)
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    DISCOVERY_COURSE_KEY_BATCH_SIZE,
    DISCOVERY_PROGRAM_KEY_BATCH_SIZE,
    LEARNER_PATHWAY,
    PROGRAM,
    REINDEX_TASK_BATCH_SIZE,
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
            return task(self, *args, **kwargs)
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
            # exec ed updates the start/end dates in additional metadata, so we have to manually
            # move that over to our variables that we use
            if metadata_record.is_exec_ed_2u_course:
                json_meta = metadata_record.json_metadata
                start_date = json_meta.get('additional_metadata', {}).get('start_date')
                end_date = json_meta.get('additional_metadata', {}).get('end_date')
                course_run_uuid = json_meta.get('advertised_course_run_uuid')
                for run in json_meta.get('course_runs'):
                    if run.get('uuid') == course_run_uuid:
                        run.update({'start': start_date, 'end': end_date})
                course_run = _get_course_run_by_uuid(json_meta, course_run_uuid)
                if course_run is not None:
                    course_run_meta = metadata_by_key.get(course_run.get('key'))
                    if hasattr(course_run_meta, 'json_metadata'):
                        course_run_meta.json_metadata.update({'start': start_date, 'end': end_date})
                        modified_content_metadata_records.append(course_run_meta)
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


def _reindex_algolia_prefix(dry_run):
    if dry_run:
        return '[ENTERPRISE_CATALOG_ALGOLIA_REINDEX] [DRY RUN]'
    else:
        return '[ENTERPRISE_CATALOG_ALGOLIA_REINDEX]'


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
def index_enterprise_catalog_in_algolia_task(self, force=False, dry_run=False):
    """
    Index course and program data in Algolia with enterprise-related fields.

    Note: It is especially important that this task uses the increased maximum ``CELERY_TASK_SOFT_TIME_LIMIT`` and
    ``CELERY_TASK_TIME_LIMIT`` as it makes somewhat time-intensive reads/writes to the database along with sending
    large payloads of data to Algolia, which was exceeding the previous default limits, causing a SoftTimeLimitExceeded
    exception.

    Args:
        force (bool): If true, forces execution of task and ignores time since last run.
        dry_run (bool): If true, does everything except call Algolia APIs.
    """
    try:
        logger.info(
            f'{_reindex_algolia_prefix(dry_run)} invoking task with arguments force={force}, dry_run={dry_run}.'
        )
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
        indexable_pathways_keys = ContentMetadata.objects.filter(
            content_type=LEARNER_PATHWAY
        ).distinct().values_list(
            'content_key',
            flat=True
        )
        indexable_content_keys = indexable_course_keys + indexable_program_keys + list(indexable_pathways_keys)
        nonindexable_content_keys = nonindexable_course_keys + nonindexable_program_keys
        _reindex_algolia(
            indexable_content_keys=indexable_content_keys,
            nonindexable_content_keys=nonindexable_content_keys,
            dry_run=dry_run,
        )
    except Exception as exep:
        logger.exception(
            f'{_reindex_algolia_prefix(dry_run)} reindex_algolia failed. Error: {exep}'
        )
        raise exep


def _precalculate_content_mappings():
    """
    Precalculate various mappings between different types of related content.

    Returns:
        2-tuple(dict):
            - First element: Mapping of program content_key to list of course run and course ContentMetadata objects.
            - Second element: Mapping of learner pathway content_key to list of program and course ContentMetadata
              objects.
    """
    program_to_courses_mapping = defaultdict(set)
    pathway_to_programs_courses_mapping = defaultdict(set)
    courses_programs = ContentMetadata.objects.filter(
        content_type__in=[COURSE, PROGRAM],
    ).prefetch_related(
        'associated_content_metadata'
    )
    for metadata in courses_programs:
        if metadata.content_type == COURSE:
            for associated_content in metadata.associated_content_metadata.all():
                if associated_content.content_type == PROGRAM:
                    program_to_courses_mapping[associated_content.content_key].add(metadata)
                elif associated_content.content_type == LEARNER_PATHWAY:
                    pathway_to_programs_courses_mapping[associated_content.content_key].add(metadata)
        # This else block represents metadata.content_type == PROGRAM
        else:
            for associated_content in metadata.associated_content_metadata.all():
                if associated_content.content_type == LEARNER_PATHWAY:
                    pathway_to_programs_courses_mapping[associated_content.content_key].add(metadata)

    return program_to_courses_mapping, pathway_to_programs_courses_mapping


def add_metadata_to_algolia_objects(
    metadata,
    algolia_products_by_object_id,
    catalog_uuids,
    customer_uuids,
    catalog_queries,
):
    """
    Convert ContentMetadata objects into Algolia products and accumulate results into `algolia_products_by_object_id`.

    At minimum, there are 3 duplicate Algolia products generated per course, one for each of [catalog uuids, customer
    uuids, catalog queries], and possibly more if any one of those exceeds ALGOLIA_UUID_BATCH_SIZE.  In the case of the
    batch size being exceeded, create further duplicate algolia product records, batching the uuids to reduce the
    payload size of the Algolia product objects.

    Args:
        metadata (ContentMetadata): The course, program or learner pathway for which to generate aloglia products.
        algolia_products_by_object_id (dict):
            Object to append the resulting algolia products to.  Keys are objectIDs, and values are algolia products to
            actually index.
        catalog_uuids (list of str): Associated catalog UUIDs.
        customer_uuids (list of str): Associated customer UUIDs.
        catalog_queries (list of tuple(str, str)): Associated catalog queries, as a list of (UUID, title) tuples.
    """

    content_key = metadata.content_key
    # add enterprise-related uuids to json_metadata
    json_metadata = copy.deepcopy(metadata.json_metadata)
    json_metadata.update({
        'objectID': get_algolia_object_id(json_metadata.get('content_type'), json_metadata.get('uuid')),
    })

    # enterprise catalog uuids
    catalog_uuids = sorted(list(catalog_uuids))
    batched_metadata = _batched_metadata(
        json_metadata,
        catalog_uuids,
        'enterprise_catalog_uuids',
        '{}-catalog-uuids-{}',
    )
    _add_in_algolia_products_by_object_id(algolia_products_by_object_id, batched_metadata)

    # enterprise customer uuids
    customer_uuids = sorted(list(customer_uuids))
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
    queries = sorted(list(catalog_queries))
    batched_metadata = _batched_metadata_with_queries(json_metadata, queries)
    _add_in_algolia_products_by_object_id(algolia_products_by_object_id, batched_metadata)


def _get_algolia_products_for_batch(
    batch_num,
    content_keys_batch,
    program_to_courses_mapping,
    pathway_to_programs_courses_mapping,
    context_accumulator,
    dry_run=False,
):
    """
    Produce a list of products to index in algolia, given a fixed length batch of content_keys.

    The intention of this function is to produce an output object that consumes a relatively fixed amount of memory.
    Callers can also maintain a fixed memory cap by only keeping a fixed number of output objects in-memory at any given
    time.

    Returns:
        list of dict: Algolia products to index.
    """
    algolia_products_by_object_id = {}

    catalog_uuids_by_key = defaultdict(set)
    customer_uuids_by_key = defaultdict(set)
    catalog_queries_by_key = defaultdict(set)

    # Create a shared convenience queryset to prefetch catalogs for all metadata lookups below.
    all_catalog_queries = CatalogQuery.objects.prefetch_related('enterprise_catalogs')

    # Retrieve ContentMetadata records for:
    # * Course runs, courses, programs and learner pathways that are directly requested, and
    # * Courses and programs indirectly related to something directly requested.
    #   - e.g. A course that was not directly requested, but is a member of a program which was requested.
    #   - e.g. A program that was not directly requested, but is a member of a pathway which was requested.
    content_metadata_no_courseruns = ContentMetadata.objects.filter(
        # All content (courses, course runs, programs, pathways) directly requested.
        Q(content_key__in=content_keys_batch)
        # All course runs, courses, or programs contained in programs or pathways requested.
        | Q(
            content_type__in=[COURSE_RUN, COURSE, PROGRAM],
            associated_content_metadata__content_type__in=[PROGRAM, LEARNER_PATHWAY],
            associated_content_metadata__content_key__in=content_keys_batch,
        )
        # All programs, pathways to which any requested course belongs.
        | Q(
            content_type__in=[PROGRAM, LEARNER_PATHWAY],
            associated_content_metadata__content_type__in=[COURSE, PROGRAM],
            associated_content_metadata__content_key__in=content_keys_batch,
        )
    ).prefetch_related(
        Prefetch('catalog_queries', queryset=all_catalog_queries),
    )

    # Retrieve ContentMetadata records for any course run which is part of any course found in the previous query.
    course_content_keys = content_metadata_no_courseruns.filter(
        content_type=COURSE,
    ).values_list('content_key', flat=True)
    content_metadata_courseruns = ContentMetadata.objects.filter(
        parent_content_key__in=course_content_keys
    ).prefetch_related(
        Prefetch('catalog_queries', queryset=all_catalog_queries),
    )

    # Combine both querysets to represent all the ContentMetadata needed to process this batch.
    #
    # DEFICIENCY: This final set does not guarantee inclusion of courses (or course runs) indirectly related to a
    # requested to a pathway via an association chain of course->program->pathway.  This maybe should be added!  When it
    # is added, a related change must be made in the third pass (below) to chain
    # `pathway_to_programs_courses_mapping` and `program_to_courses_mapping` to actually collect the UUIDs.
    content_metadata_to_process = content_metadata_no_courseruns.union(content_metadata_courseruns)

    # First pass over the batch of content.  The goal for this pass is to collect all the UUIDs directly associated with
    # each content.  This DOES NOT capture any UUIDs indirectly related to programs or pathways via associated courses
    # or programs.
    for metadata in content_metadata_to_process:
        if metadata.content_type in (COURSE, PROGRAM, LEARNER_PATHWAY):
            content_key = metadata.content_key
        else:
            # Course runs should contribute their UUIDs to the parent course.
            content_key = metadata.parent_content_key
        associated_catalog_queries = metadata.catalog_queries.all()
        for catalog_query in associated_catalog_queries:
            catalog_queries_by_key[content_key].add((str(catalog_query.uuid), catalog_query.title))
            # This line is possible thanks to `all_catalog_queries` with the prefectch_related() above.
            associated_catalogs = catalog_query.enterprise_catalogs.all()
            for catalog in associated_catalogs:
                catalog_uuids_by_key[content_key].add(str(catalog.uuid))
                customer_uuids_by_key[content_key].add(str(catalog.enterprise_uuid))

    # Second pass.  This time the goal is to capture indirect relationships on programs:
    #  * For each program:
    #    - Absorb all UUIDs associated with every associated course.
    for metadata in content_metadata_to_process:
        if metadata.content_type != PROGRAM:
            continue
        program_content_key = metadata.content_key
        for metadata in program_to_courses_mapping[program_content_key]:
            catalog_queries_by_key[program_content_key].update(catalog_queries_by_key[metadata.content_key])
            catalog_uuids_by_key[program_content_key].update(catalog_uuids_by_key[metadata.content_key])
            customer_uuids_by_key[program_content_key].update(customer_uuids_by_key[metadata.content_key])

    # Third pass.  This time the goal is to capture indirect relationships on pathways:
    #  * For each pathway:
    #    - Absorb all UUIDs associated with every associated course.
    #    - Absorb all UUIDs associated with every associated program.
    for metadata in content_metadata_to_process:
        if metadata.content_type != LEARNER_PATHWAY:
            continue
        pathway_content_key = metadata.content_key

        for metadata in pathway_to_programs_courses_mapping[pathway_content_key]:
            catalog_queries_by_key[pathway_content_key].update(catalog_queries_by_key[metadata.content_key])
            catalog_uuids_by_key[pathway_content_key].update(catalog_uuids_by_key[metadata.content_key])
            customer_uuids_by_key[pathway_content_key].update(customer_uuids_by_key[metadata.content_key])

            # Extra disabled logic to additionally absorb UUIDs from courses linked to this pathway indirectly via a
            # program (chain of association is course -> program -> pathway).  This doesn't work because
            # content_metadata_to_process queryset for this batch has insuficcient records to support this feature.
            #
            # if metadata.content_type == PROGRAM:
            #     for course_metadata in program_to_courses_mapping[metadata.content_key]:
            #         catalog_queries_by_key[pathway_content_key].update(
            #             catalog_queries_by_key[course_metadata.content_key]
            #         )
            #         catalog_uuids_by_key[pathway_content_key].update(
            #             catalog_uuids_by_key[course_metadata.content_key]
            #         )
            #         customer_uuids_by_key[pathway_content_key].update(
            #             customer_uuids_by_key[course_metadata.content_key]
            #         )

    # iterate over courses, programs and pathways and add their metadata to the list of objects to be indexed
    content_metadata_to_index = (
        metadata for metadata in content_metadata_to_process
        if metadata.content_type in [COURSE, PROGRAM, LEARNER_PATHWAY]
    )
    num_content_metadata_indexed = 0
    for metadata in content_metadata_to_index:
        # TODO: remove when https://2u-internal.atlassian.net/browse/ENT-7458 is resolved
        if 'GTx+MGT6203x' in content_key:
            logger.info(
                f'[ENT-7458] {content_key} will be added to Algolia index'
            )
        # Check if we've indexed the course recently
        # (programs/pathways are indexed every time regardless of last indexing)
        if _was_recently_indexed(metadata.content_key) and metadata.content_type not in [PROGRAM, LEARNER_PATHWAY]:
            continue

        # Build all the algolia products for this single metadata record and append them to
        # `algolia_products_by_object_id`.  This function contains all the logic to create duplicate/segmented records
        # with non-overlapping UUID list fields to keep the product size below a fixed limit controlled by
        # ALGOLIA_UUID_BATCH_SIZE.
        add_metadata_to_algolia_objects(
            metadata,
            algolia_products_by_object_id,
            catalog_uuids_by_key[metadata.content_key],
            customer_uuids_by_key[metadata.content_key],
            catalog_queries_by_key[metadata.content_key],
        )

        num_content_metadata_indexed += 1

    # In case there are multiple CourseMetadata records that share the exact same content_uuid (which would cause an
    # algolia objectID collision), do not send more than one.  Note that selection of duplicate content is
    # non-deterministic because we do not use order_by() on the queryset.
    context_accumulator.setdefault('generated_algolia_object_ids', set())
    duplicate_algolia_records_discarded = 0
    candidate_algolia_object_ids = list(algolia_products_by_object_id.keys())
    for algolia_object_id in candidate_algolia_object_ids:
        if algolia_object_id in context_accumulator['generated_algolia_object_ids']:
            del algolia_products_by_object_id[algolia_object_id]
            context_accumulator['discarded_algolia_object_ids'][algolia_object_id] += 1
            duplicate_algolia_records_discarded += 1
    context_accumulator['generated_algolia_object_ids'].update(algolia_products_by_object_id.keys())

    # Increment counter used for logging at the very end.
    context_accumulator['total_algolia_products_count'] += len(algolia_products_by_object_id)

    logger.info(
        f'{_reindex_algolia_prefix(dry_run)} '
        f'batch#{batch_num}: '
        f'{len(content_keys_batch)} content keys, '
        f'{content_metadata_to_process.count()} content metadata found, '
        f'{num_content_metadata_indexed} content metadata indexed, '
        f'{len(algolia_products_by_object_id)} generated algolia products kept, '
        f'{duplicate_algolia_records_discarded} generated algolia products discarded.'
    )

    # extract only the fields we care about.
    return create_algolia_objects(algolia_products_by_object_id.values(), ALGOLIA_FIELDS)


def _index_content_keys_in_algolia(content_keys, algolia_client, dry_run=False):
    """
    Determines list of Algolia objects to include in the Algolia index based on the
    specified content keys, and replaces all existing objects with the new ones in an atomic reindex.

    Memory consumption of this function follows a sawtooth pattern over time.  Maximum instantaneous memory consumption
    is dictated by the larger of two batch sizes:

    * The number of algolia products generated by a batch of `REINDEX_TASK_BATCH_SIZE` content keys.  This number is
      variable, but at the time of writing this was on order of 180 (with `REINDEX_TASK_BATCH_SIZE` = 10).
    * The algoliasearch library batch size, default 1000.

    Arguments:
        content_keys (list): List of indexable content_key strings.
        algolia_client: Instance of an Algolia API client, or None if dry_run is enabled.
    """
    logger.info(
        f'{_reindex_algolia_prefix(dry_run)} There are {len(content_keys)} total content keys to include in the'
        f' Algolia index.'
    )
    (
        program_to_courses_mapping,
        pathway_to_programs_courses_mapping,
    ) = _precalculate_content_mappings()
    context_accumulator = {
        'total_algolia_products_count': 0,
        'discarded_algolia_object_ids': defaultdict(int),
    }
    # Produce a generator of batches of algolia products to index.  Each batch has an unpredictable, variable length.
    # Not immediately evaluated, so no memory is consumed yet.
    algolia_products_batch_generator = (
        _get_algolia_products_for_batch(
            batch_num,
            content_keys_batch,
            program_to_courses_mapping,
            pathway_to_programs_courses_mapping,
            context_accumulator,
            dry_run=dry_run,
        )
        for batch_num, content_keys_batch
        in enumerate(batch(content_keys, batch_size=REINDEX_TASK_BATCH_SIZE))
    )
    # Flatten the variable-length batches of products into a flat iterable of all products to index.  Whatever consumes
    # this will not even know that it was already batched and recombined.
    # Still not evaluated, so no memory is consumed yet.
    algolia_products_generator = (
        algolia_product
        for batch in algolia_products_batch_generator
        for algolia_product in batch
    )

    # Feed the un-evaluated flat iterable of algolia products into the 3rd party library function.  As of this writing,
    # this library function will chunk the interable again using a default batch size of 1000.
    #
    # See function documentation for indication that an Iterator is accepted:
    # https://github.com/algolia/algoliasearch-client-python/blob/e0a2a578464a1b01caaa84dba927b99ae8476af3/algoliasearch/search_index.py#L89
    if not dry_run:
        algolia_client.replace_all_objects(algolia_products_generator)
    else:
        logger.info(
            f'{_reindex_algolia_prefix(dry_run)} skipping algolia_client.replace_all_objects().'
        )
        # Force evaluation of the generator to simulate algolia client reading it.
        _ = list(algolia_products_generator)

    # Now, the generator will have been fully evaluated, and context_accumulator will have been filled with interesting
    # metrics.
    if context_accumulator['discarded_algolia_object_ids']:
        top_10_discarded_algolia_object_ids = \
            sorted(context_accumulator['discarded_algolia_object_ids'].items(), key=itemgetter(1), reverse=True)[:10]
        logger.info(
            f'{_reindex_algolia_prefix(dry_run)} Histogram of top 10 most frequently discarded algolia object IDs: '
            f'{top_10_discarded_algolia_object_ids}.'
        )
    logger.info(
        f'{_reindex_algolia_prefix(dry_run)} {context_accumulator["total_algolia_products_count"]} products found.'
    )


def _reindex_algolia(indexable_content_keys, nonindexable_content_keys, dry_run=False):
    """
    Indexes courses, programs and pathways metadata in the Algolia search index.
    """
    # NOTE: this log message is used in a Splunk alert and should remain consistent in its language
    logger.info(
        f'{_reindex_algolia_prefix(dry_run)} There are %s indexable content keys, which will replace all existing'
        ' objects in the Algolia index. %s nonindexable content keys will be removed.',
        len(indexable_content_keys), len(nonindexable_content_keys),
    )
    if len(indexable_content_keys) == 0:
        logger.warning('Skipping Algolia indexing as there are no indexable content keys.')
        # ensure we do not continue the indexing task if there are no indexable content keys. this
        # will help prevent us from unintentionally removing all content keys from the index.
        return

    algolia_client = None
    if not dry_run:
        algolia_client = get_initialized_algolia_client()
        configure_algolia_index(algolia_client)

    # Replaces all objects in the Algolia index with new objects based on the specified
    # indexable content keys.
    _index_content_keys_in_algolia(
        content_keys=indexable_content_keys,
        algolia_client=algolia_client,
        dry_run=dry_run,
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
    start_time = time.perf_counter()
    try:
        catalog_query = CatalogQuery.objects.get(id=catalog_query_id)
    except CatalogQuery.DoesNotExist:
        logger.error('Could not find a CatalogQuery with id %s', catalog_query_id)

    try:
        associated_content_keys = update_contentmetadata_from_discovery(catalog_query)
    except Exception as e:
        logger.exception(
            f'Something went wrong while updating content metadata from discovery using catalog: {catalog_query_id} '
            f'after update_catalog_metadata_task_seconds={time.perf_counter()-start_time} seconds',
            exc_info=e,
        )
        raise e
    logger.info(
        f'Finished update_catalog_metadata_task with {len(associated_content_keys)} '
        f'associated content keys for catalog {catalog_query_id} '
        f'after update_catalog_metadata_task_seconds={time.perf_counter()-start_time} seconds'
    )


@shared_task(base=LoggedTaskWithRetry, bind=True)
@expiring_task_semaphore()
def fetch_missing_course_metadata_task(self, force=False):  # pylint: disable=unused-argument
    """
    Creates a CatalogQuery for all the courses that do not have ContentMetadata instance.

    After creating the catalog query it calls update_contentmetadata_from_discovery to update the metadata for these
    courses. Course metadata is only missing for program courses so the initial query only looks for course metadata
    that are embedded inside a program.
    """
    logger.info('[FETCH_MISSING_METADATA] fetch_missing_course_metadata_task task started.')
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
    if missing_course_keys:
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
        logger.info('[FETCH_MISSING_METADATA] Finished fetch_missing_course_metadata_task with {} associated content '
                    'keys for catalog {}'.format(len(associated_content_keys), catalog_query.id))
    else:
        logger.info('[FETCH_MISSING_METADATA] No missing key found in fetch_missing_course_metadata_task')


@shared_task(base=LoggedTaskWithRetry, bind=True)
@expiring_task_semaphore()
def fetch_missing_pathway_metadata_task(self, force=False):  # pylint: disable=unused-argument
    """
    Creates ContentMetadata for Learner Pathways and all its associates.

    These steps are performed to load data for Learner Pathways:
    1. Loads All the Learner Pathways ContentMetadata records from the discovery
    2. Loads the missing associated programs from the discovery
    3. Loads the missing the associated courses from the discovery
    4. Update associations between pathways and relevant course and programs

    Note: We need to load all the LEARNER_PATHWAYS here because we don't have the information about the associations
    with learner_pathways in course or programs json_metadata. Here we are loading all of them and linking with Course
    # ContentMetadata and Program ContentMetadata
    """
    logger.info('[FETCH_MISSING_METADATA] fetch_missing_pathway_metadata_task task started.')
    content_filter = {
        'content_type': LEARNER_PATHWAY,
    }
    catalog_query, _ = CatalogQuery.objects.get_or_create(
        content_filter_hash=get_content_filter_hash(content_filter),
        defaults={'content_filter': content_filter, 'title': None},
    )
    associated_content_keys = update_contentmetadata_from_discovery(catalog_query)
    logger.info(
        '[FETCH_MISSING_METADATA] Finished Pathways fetch_missing_pathway_metadata_task with {} associated content '
        'keys for catalog {}'.format(
            len(associated_content_keys), catalog_query.id
        )
    )

    learner_pathway_metadata_list = ContentMetadata.objects.filter(content_type=LEARNER_PATHWAY).values_list(
        'json_metadata', flat=True,
    )
    program_uuids = set()
    course_keys = set()
    for learner_pathway_metadata in learner_pathway_metadata_list:
        program_uuids.update(get_pathway_program_uuids(learner_pathway_metadata))
        course_keys.update(get_pathway_course_keys(learner_pathway_metadata))

    # Check which programs do not have content metadata.
    present_program_uuids = ContentMetadata.objects.filter(
        content_type=PROGRAM, content_key__in=program_uuids
    ).values_list(
        'content_key', flat=True
    )

    missing_program_uuids = program_uuids.difference(present_program_uuids)
    if missing_program_uuids:
        content_filter = {
            'status': 'published',
            'key': list(missing_program_uuids),
            'content_type': PROGRAM,
        }
        catalog_query, _ = CatalogQuery.objects.get_or_create(
            content_filter_hash=get_content_filter_hash(content_filter),
            defaults={'content_filter': content_filter, 'title': None},
        )

        associated_content_keys = update_contentmetadata_from_discovery(catalog_query)
        logger.info(
            '[FETCH_MISSING_METADATA] Finished programs fetch_missing_pathway_metadata_task with {} keys for '
            'catalog {}'.format(
                len(associated_content_keys), catalog_query.id
            )
        )

    # Check which courses do not have content metadata.
    present_course_keys = ContentMetadata.objects.filter(
        content_type=COURSE, content_key__in=course_keys
    ).values_list(
        'content_key', flat=True
    )

    missing_course_keys = course_keys.difference(present_course_keys)
    if missing_course_keys:
        content_filter = {
            'status': 'published',
            'key': list(missing_course_keys),
            'content_type': COURSE,
        }

        catalog_query, _ = CatalogQuery.objects.get_or_create(
            content_filter_hash=get_content_filter_hash(content_filter),
            defaults={'content_filter': content_filter, 'title': None},
        )

        associated_content_keys = update_contentmetadata_from_discovery(catalog_query)
        logger.info(
            '[FETCH_MISSING_METADATA] Finished courses fetch_missing_pathway_metadata_task with {} keys for '
            'catalog {}'.format(
                len(associated_content_keys), catalog_query.id
            )
        )

    # update association between pathways and its associated programs and courses.
    for pathway in ContentMetadata.objects.filter(content_type=LEARNER_PATHWAY):
        if pathway.json_metadata['visible_via_association'] and pathway.json_metadata['status'] == 'active':
            course_keys = get_pathway_course_keys(pathway.json_metadata)
            program_uuids = get_pathway_program_uuids(pathway.json_metadata)
            associated_content_metadata = ContentMetadata.objects.filter(
                content_key__in=program_uuids + course_keys
            )
            pathway.associated_content_metadata.set(associated_content_metadata)
            logger.info(
                '[FETCH_MISSING_METADATA] Learner Pathway {} associated created. No. of associations: {}'.format(
                    pathway.content_key,
                    pathway.associated_content_metadata.count(),
                )
            )
        else:
            pathway.associated_content_metadata.clear()

    logger.info('[FETCH_MISSING_METADATA] fetch_missing_pathway_metadata_task execution completed.')
