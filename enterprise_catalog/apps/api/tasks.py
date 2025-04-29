import copy
import functools
import json
import logging
import re
import sys
import time
from collections import defaultdict
from datetime import timedelta, datetime
from operator import itemgetter

from algoliasearch.exceptions import AlgoliaException
from celery import shared_task, states
from celery.exceptions import Ignore
from celery_utils.logged_task import LoggedTask
from django.conf import settings
from django.db import IntegrityError
from django.db.models import Prefetch, Q
from django.db.utils import OperationalError
from django_celery_results.models import TaskResult
from requests.exceptions import ConnectionError as RequestsConnectionError

from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.algolia_utils import (
    ALGOLIA_FIELDS,
    ALGOLIA_JSON_METADATA_MAX_SIZE,
    ALGOLIA_UUID_BATCH_SIZE,
    _algolia_object_from_product,
    configure_algolia_index,
    create_algolia_objects,
    get_algolia_object_id,
    get_initialized_algolia_client,
    get_pathway_course_keys,
    get_pathway_program_uuids,
    partition_course_keys_for_indexing,
    partition_program_keys_for_indexing,
    new_search_client_or_error,
)
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
    FORCE_INCLUSION_METADATA_TAG_KEY,
    LEARNER_PATHWAY,
    PROGRAM,
    QUERY_FOR_RESTRICTED_RUNS,
    REINDEX_TASK_BATCH_SIZE,
    TASK_BATCH_SIZE,
    VIDEO,
)
from enterprise_catalog.apps.catalog.content_metadata_utils import (
    transform_course_metadata_to_visible,
)
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    create_course_associated_programs,
    update_contentmetadata_from_discovery,
)
from enterprise_catalog.apps.catalog.serializers import (
    NormalizedContentMetadataSerializer,
)
from enterprise_catalog.apps.catalog.utils import (
    batch,
    get_content_filter_hash,
    localized_utcnow,
)
from enterprise_catalog.apps.video_catalog.models import Video


logger = logging.getLogger(__name__)

ONE_HOUR = timedelta(hours=1)

UNREADY_TASK_RETRY_COUNTDOWN_SECONDS = 60 * 5

# ENT-4980 every batch "shard" record in Algolia should have all of these that pertain to the course
EXPLORE_CATALOG_TITLES = ['A la carte', 'Subscription']


def _fetch_courses_by_keys(course_keys, extra_query_params=None):
    """
    Fetches course data from discovery's /api/v1/courses endpoint for the provided course keys.

    Args:
        course_keys (list of str): Content keys for Course ContentMetadata objects.
    Returns:
        list of dict: Returns a list of dictionaries where each dictionary represents the course data from discovery.
    """
    return DiscoveryApiClient().fetch_courses_by_keys(course_keys, extra_query_params=extra_query_params)


def _fetch_programs_by_keys(program_keys):
    """
    Fetches program data from discovery's /api/v1/programs endpoint for the provided program keys.

    Args:
        program_keys (list of str): Content keys for Program ContentMetadata objects.
    Returns:
        list of dict: Returns a list of dictionaries where each dictionary represents the program data from discovery.
    """
    return DiscoveryApiClient().fetch_programs_by_keys(program_keys)


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
    # 2025-03-10: we recently switched to celery protocol 2, and django-celery-results
    # gives preference to `kwargsrepr` over `kwargs` when persisting results. So we have
    # to json-serialize the repr() of the task args/kwargs in order for our lookup of
    # recent tasks with the same name and input. This is ok to do because none of the task
    # invocations in this code repo specify a custom args/kwargsrepr when submitting tasks, and
    # celery uses the repr() function as the default. See references:
    # https://github.com/celery/django-celery-results/issues/113
    # https://docs.celeryq.dev/en/stable/internals/protocol.html
    # https://github.com/celery/django-celery-results/blob/main/django_celery_results/backends/database.py

    # Furthermore, django-celery-results creates the TaskResult
    # record before it's submitted to the worker. At that point, args is a tuple, but when serialized
    # into the worker, kwargs is a list. So here, in the worker, we have to coerce args to a tuple.
    args_lookup = json.dumps(repr(tuple(task_object.request.args)))
    kwargs_lookup = json.dumps(repr(task_object.request.kwargs))
    threshold = localized_utcnow() - time_delta
    logger.info(
        'Task name %s, args %s, args_lookup %s, kwargs %s, kwargs_lookup %s, threshold %s',
        task_object.name, task_object.request.args, args_lookup,
        task_object.request.kwargs, kwargs_lookup, threshold,
    )
    return TaskResult.objects.filter(
        task_name=task_object.name,
        task_args=args_lookup,
        task_kwargs=kwargs_lookup,
        date_created__gte=threshold,
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
def update_full_content_metadata_task(self, force=False, dry_run=False):  # pylint: disable=unused-argument
    """
    Looks up the full metadata from discovery's `/api/v1/courses` and `/api/v1/programs` endpoints to pad all
    ContentMetadata objects. The metadata is merged with the existing contents
    of the json_metadata field for each ContentMetadata record.

    Args:
        force (bool): If true, forces execution of task and ignores time since last run.
    """

    content_keys = [metadata.content_key for metadata in ContentMetadata.objects.filter(content_type=COURSE)]
    _update_full_content_metadata_course(content_keys, dry_run)
    content_keys = [metadata.content_key for metadata in ContentMetadata.objects.filter(content_type=PROGRAM)]
    _update_full_content_metadata_program(content_keys, dry_run)


def _update_full_content_metadata_course(content_keys, dry_run=False):
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

        fetched_course_keys = [course['key'] for course in full_course_dicts]
        course_reviews_by_content_key = DiscoveryApiClient().get_course_reviews(fetched_course_keys)
        metadata_by_key = _get_course_records_by_key(fetched_course_keys)

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

            course_review = course_reviews_by_content_key.get(content_key)
            modified_course_record = _update_single_full_course_record(
                course_metadata_dict, metadata_record, course_review, dry_run
            )
            modified_content_metadata_records.append(modified_course_record)

            program_content_keys = create_course_associated_programs(
                course_metadata_dict.get('programs', []),
                modified_course_record,
            )
            _update_full_content_metadata_program(program_content_keys, dry_run)

            _update_full_restricted_course_metadata(modified_course_record, course_review, dry_run)

        if dry_run:
            logger.info('dry_run=True, not updating course metadata')
        else:
            ContentMetadata.objects.bulk_update(
                modified_content_metadata_records,
                ['_json_metadata'],
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


def _update_full_restricted_course_metadata(modified_metadata_record, course_review, dry_run):
    """
    For all restricted courses whose parent is ``modified_metadata_record``, does a full
    update of metadata and restricted run relationships.
    """
    restricted_courses = list(modified_metadata_record.restricted_courses.all())
    if not restricted_courses:
        return

    # Fetch from /api/v1/courses with restricted content included
    metadata_list = _fetch_courses_by_keys(
        [modified_metadata_record.content_key],
        extra_query_params=QUERY_FOR_RESTRICTED_RUNS,
    )
    if not metadata_list:
        raise Exception(
            f'No restricted course metadata could be fetched for {modified_metadata_record.content_key}'
        )

    full_restricted_metadata = metadata_list[0]

    for restricted_course in restricted_courses:
        # First, update the restricted course record's json metadata to use the full metadata
        # from above.
        restricted_course.update_metadata(full_restricted_metadata, is_full_update=True)

        # Last, run the "standard" transformations below to update with the full
        # course metadata, do normalization, etc.
        _update_single_full_course_record(
            full_restricted_metadata, restricted_course, course_review, dry_run, skip_json_metadata_update=True,
        )
        restricted_course.save()


def _get_course_records_by_key(fetched_course_keys):
    """
    Helper to fetch a dict of course `ContentMetadata` records by content key.
    """
    metadata_records_for_fetched_keys = ContentMetadata.objects.filter(
        content_key__in=fetched_course_keys,
    )
    return {
        metadata.content_key: metadata
        for metadata in metadata_records_for_fetched_keys
    }


def _update_single_full_course_record(
    course_metadata_dict, metadata_record, course_review, dry_run, skip_json_metadata_update=False,
):
    """
    Given a fetched dictionary of course content metadata and an option `course_review` record,
    updates an existing course `ContentMetadata` instance with the "full" dictionary of `json_metadata`
    for that course.
    """
    if not skip_json_metadata_update:
        # Merge the full metadata from discovery's /api/v1/courses into the local metadata object.
        metadata_record._json_metadata.update(course_metadata_dict)  # pylint: disable=protected-access

    _normalize_metadata_record(metadata_record)

    if course_review:
        # pylint: disable=protected-access
        metadata_record._json_metadata['reviews_count'] = course_review.get('reviews_count')
        metadata_record._json_metadata['avg_course_rating'] = course_review.get('avg_course_rating')

    if metadata_record.json_metadata.get(FORCE_INCLUSION_METADATA_TAG_KEY):
        metadata_record.json_metadata = transform_course_metadata_to_visible(metadata_record.json_metadata)

    if dry_run:
        logger.info('[Dry Run] Updated course content metadata json for {}: {}'.format(
            metadata_record.content_key, json.dumps(metadata_record.json_metadata)
        ))

    return metadata_record


def _normalize_metadata_record(course_metadata_record):
    """
    Perform more steps to normalize and move keys around
    for more consistency across content types.
    """
    normalized_metadata_input = {
        'course_metadata': course_metadata_record.json_metadata,
    }
    # pylint: disable=protected-access
    course_metadata_record._json_metadata['normalized_metadata'] =\
        NormalizedContentMetadataSerializer(normalized_metadata_input).data
    course_metadata_record._json_metadata['normalized_metadata_by_run'] = {}
    for run in course_metadata_record.json_metadata.get('course_runs', []):
        course_metadata_record._json_metadata['normalized_metadata_by_run'].update({
            run['key']: NormalizedContentMetadataSerializer({
                'course_run_metadata': run,
                'course_metadata': course_metadata_record.json_metadata,
            }).data
        })


def _update_full_content_metadata_program(content_keys, dry_run=False):
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

            metadata_record._json_metadata.update(program_metadata_dict)  # pylint: disable=protected-access
            modified_content_metadata_records.append(metadata_record)

        if dry_run:
            logger.info('dry_run=true, not updating program metadata')
        else:
            ContentMetadata.objects.bulk_update(
                modified_content_metadata_records,
                ['_json_metadata'],
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
def index_enterprise_catalog_in_algolia_task(self, force=False, dry_run=False):  # pylint: disable=unused-argument
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
        courses_content_metadata = ContentMetadata.objects.filter(content_type=COURSE)
        # Make sure the courses we consider for indexing actually contain restricted runs so that
        # "unicorn" courses (i.e. courses that contain only restricted runs) do not get discarded by
        # partition_course_keys_for_indexing() for not having an advertised run.
        if getattr(settings, 'SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS', False):
            courses_content_metadata = courses_content_metadata.prefetch_restricted_overrides()
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


def _created_between(datestring, min_days_ago, max_days_ago):
    if not datestring:
        return False
    created_timestamp = datetime.strptime(datestring, '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()
    difference_in_days = (time.time() - created_timestamp) / (60 * 60 * 24)
    if difference_in_days > min_days_ago and difference_in_days < max_days_ago:
        return True
    return False


def _retrieve_inactive_tmp_indices(client):
    indices = client.list_indices().get('items', [])
    tmp_indices = filter(lambda x: x.get('name', '').startswith(f'{settings.ALGOLIA["INDEX_NAME"]}_tmp_'), indices)
    inactive_tmp_indices = filter(lambda x: _created_between(x.get('createdAt', None), 10, 60), tmp_indices)
    return list(map(lambda x: x.get('name', ''), inactive_tmp_indices))


def _delete_indices(client, indices, dry_run=True):
    logger.info('Index names to delete: %s', indices)

    if dry_run:
        logger.info('dry_run=true, not deleting old tmp indices from Algolia')
        return indices

    for index_name in indices:
        try:
            logger.info('Deleting index: %s', index_name)
            client.init_index(index_name).delete()
            logger.info('Deleted index: %s', index_name)
        except Exception as exep:
            logger.exception(
                f'Deleting index: {index_name} failed. Error: {exep}'
            )
            raise exep

        logger.info('Finished deleting indices from Algolia')


@shared_task(base=LoggedTaskWithRetry, bind=True, default_retry_delay=UNREADY_TASK_RETRY_COUNTDOWN_SECONDS)
@expiring_task_semaphore()
def remove_old_temporary_catalog_indices_task(self, force=False, dry_run=True):  # pylint: disable=unused-argument
    """
    Remove old temporary catalog indices from Algolia.

    Because Algolia's `replace_all_objects` method generates but does not delete temporary indices
    named as `<index_name>_tmp_<timestamp>`, we need to remove them periodically.
    This task removes all indices that are older than 10 days and newer than 60 days.

    Args:
        force (bool): Not used.
        dry_run (bool): If true, does everything except call Algolia APIs.
    """
    client = None
    logger.info(
        f'Invoking `remove_old_temporary_catalog_indices` task with arguments force={force}, dry_run={dry_run}.'
    )

    try:
        # `get_initialized_algolia_client` is not what we need here
        # because that is initialized to the wrong index.
        client = new_search_client_or_error()
    except (AlgoliaException, TypeError) as exep:
        logger.exception(
            f'Creating Algolia client failed. Error: {exep}'
        )
        raise exep

    try:
        inactive_tmp_indices = _retrieve_inactive_tmp_indices(client)
    except Exception as exep:
        logger.exception(
            f'Retrieving old tmp indices from Algolia failed. Error: {exep}'
        )
        raise exep

    _delete_indices(client, inactive_tmp_indices, dry_run)

    return inactive_tmp_indices


def _precalculate_content_mappings():
    """
    Precalculate various mappings between different types of related content.

    NOTE: this method is naive, and does not take into account the indexability of content.  I.e. it will happily tell
    you that courses A, B, and C are part of program P even though courses B and C have already ended.

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


def add_video_to_algolia_objects(
    video,
    algolia_products_by_object_id,
    customer_uuids,
    catalog_uuids,
    catalog_queries,
):
    """
    Convert Video objects into Algolia products and accumulate results into `algolia_products_by_object_id`.

    Duplicate Algolia products generated per video for customer uuids, and possibly more if any one of those
    exceeds ALGOLIA_UUID_BATCH_SIZE.  In the case of the batch size being exceeded, create further duplicate
    algolia product records, batching the uuids to reduce the payload size of the Algolia product objects.

    Args:
        video (Video): The video for which to generate aloglia products.
        algolia_products_by_object_id (dict):
            Object to append the resulting algolia products to.  Keys are objectIDs, and values are algolia products to
            actually index.
        customer_uuids (list of str): Associated customer UUIDs.
        catalog_uuids (list of str): Associated catalog UUIDs.
        catalog_queries (list of tuple(str, str)): Associated catalog queries, as a list of (UUID, title) tuples.
    """
    # add enterprise-related uuids to json_metadata
    json_metadata = copy.deepcopy(video.json_metadata)
    json_metadata.update({
        'objectID': f'video-{video.edx_video_id}',
    })
    json_metadata.update({
        'content_type': VIDEO,
    })
    json_metadata.update({
        'aggregation_key': video.edx_video_id,
    })
    json_metadata.update({
        'video_usage_key': video.video_usage_key,
    })
    json_metadata.update({
        'title': video.title,
    })
    json_metadata_size = sys.getsizeof(
        json.dumps(_algolia_object_from_product(json_metadata, algolia_fields=ALGOLIA_FIELDS)).strip(" "),
    )
    # Algolia limits the size of algolia object records and measures object size as stated in:
    # https://support.algolia.com/hc/en-us/articles/4406981897617-Is-there-a-size-limit-for-my-index-records
    # Refrain from adding the video record to the list of objects to index if the video exceeds the max size
    # allowed.
    if json_metadata_size > ALGOLIA_JSON_METADATA_MAX_SIZE:
        logger.warning(
            f"add_video_to_algolia_objects found a video record: {video.edx_video_id} who's sized exceeded the maximum"
            f"algolia object size of {ALGOLIA_JSON_METADATA_MAX_SIZE} bytes"
        )
        return

    # enterprise customer uuids
    customer_uuids = sorted(list(customer_uuids))
    batched_metadata = _batched_metadata(
        json_metadata,
        customer_uuids,
        'enterprise_customer_uuids',
        '{}-customer-uuids-{}',
    )
    _add_in_algolia_products_by_object_id(algolia_products_by_object_id, batched_metadata)

    # enterprise catalog uuids
    catalog_uuids = sorted(list(catalog_uuids))
    batched_metadata = _batched_metadata(
        json_metadata,
        catalog_uuids,
        'enterprise_catalog_uuids',
        '{}-catalog-uuids-{}',
    )
    _add_in_algolia_products_by_object_id(algolia_products_by_object_id, batched_metadata)

    queries = sorted(list(catalog_queries))
    batched_metadata = _batched_metadata_with_queries(json_metadata, queries)
    _add_in_algolia_products_by_object_id(algolia_products_by_object_id, batched_metadata)


def add_metadata_to_algolia_objects(
    metadata,
    algolia_products_by_object_id,
    catalog_uuids,
    customer_uuids,
    catalog_queries,
    academy_uuids,
    academy_tags,
    video_ids,
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
        academy_uuids (list of str): Associated academy UUIDs.
        academy_tags (list of str): Associated academy tags.
        catalog_queries (list of tuple(str, str)): Associated catalog queries, as a list of (UUID, title) tuples.
    """
    # add enterprise-related uuids to json_metadata
    json_metadata = copy.deepcopy(metadata.json_metadata)
    json_metadata.update({
        'objectID': get_algolia_object_id(json_metadata.get('content_type'), json_metadata.get('uuid')),
    })
    # academy uuids and tags are always less than 15 in number
    json_metadata.update({
        'academy_uuids': list(academy_uuids),
    })
    json_metadata.update({
        'academy_tags': list(academy_tags),
    })
    json_metadata.update({
        'video_ids': list(video_ids),
    })

    json_metadata_size = sys.getsizeof(
        json.dumps(_algolia_object_from_product(json_metadata, algolia_fields=ALGOLIA_FIELDS)).strip(" "),
    )
    # Algolia limits the size of algolia object records and measures object size as stated in:
    # https://support.algolia.com/hc/en-us/articles/4406981897617-Is-there-a-size-limit-for-my-index-records
    # Refrain from adding the metadata record to the list of objects to index if the metadata exceeds the max size
    # allowed.
    if json_metadata_size > ALGOLIA_JSON_METADATA_MAX_SIZE:
        content = json_metadata.get('aggregation_key') or json_metadata.get('title')
        logger.warning(
            f"add_metadata_to_algolia_objects found a metadata record: {content} who's sized exceeded the maximum"
            f"algolia object size of {ALGOLIA_JSON_METADATA_MAX_SIZE} bytes"
        )
        return

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

    # enterprise catalog queries (tuples of (query uuid, query title)), note: account for None being present
    # within the list
    queries = sorted(list(catalog_queries))
    batched_metadata = _batched_metadata_with_queries(json_metadata, queries)
    _add_in_algolia_products_by_object_id(algolia_products_by_object_id, batched_metadata)


def get_algolia_objects_from_course_content_metadata(content_metadata):
    content_key = content_metadata.content_key
    context_accumulator = {
        'total_algolia_products_count': 0,
        'discarded_algolia_object_ids': defaultdict(int),
    }
    algolia_product = _get_algolia_products_for_batch(0, [content_key], {content_key}, {}, {}, context_accumulator)
    logger.info(
        f"get_algolia_objects_from_course_content_metadata created algolia object: {algolia_product} for course: "
        f"{content_key} with context: {context_accumulator}"
    )
    return algolia_product


# pylint: disable=too-many-statements
def _get_algolia_products_for_batch(
    batch_num,
    content_keys_batch,
    all_indexable_content_keys,
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

    Business logic notes:

    * ONLY objects that are indexable are indexed.
    * Course runs are never indexed, but they still contribute their catalog/customer UUIDs to higher level objects
      (courses, programs, pathways).
    * UUIDs are inherited all the way from course runs to courses to programs to pathways.  Specifically, a given object
      in the tree will be indexed with union of all UUIDs from every node in the sub-tree.  E.g. a pathway object will
      be indexed with the UUIDs found on the pathway + program + course + course run beneath.
    * If a course is part of a program, but only the program is in a given catalog, that catalog will only be indexed as
      part of the program. That means the program will only be searchable via the catalog or customer of that catalog,
      but not the containing course, possibly hiding content from search results that are actually accessible. It might
      be worth re-assessing this logic to determine if it's correct.

    Args
        batch_num (int): The numeric identifier of the current batch, defined by the contents of `content_keys_batch`.
        content_keys_batch (list or str):
            The content keys to process for this batch.  It is possible that this batch will index more objects to
            Algolia than what is contained in `content_keys_batch`; e.g. if the batch contains a program which in turn
            contains an indexable course, that course will be "pulled into" this batch.
        all_indexable_content_keys (set of str):
            All indexable content keys across all batches.  Must be a python set to support quick lookups.
        program_to_courses_mapping (dict of str -> list of str): Mapping of programs to the courses within.
        pathway_to_programs_courses_mapping (dict of str -> list of str):
            Mapping of pathways to programs and courses within.
        context_accumulator (dict):
            An object that is passed to every batch in order to enable accumulating context and metrics that can be
            useful for logging.
        dry_run (bool): If true, all logic will run except sending products to Algolia.

    Returns:
        list of dict: Algolia products to index.
    """
    algolia_products_by_object_id = {}

    catalog_uuids_by_key = defaultdict(set)
    customer_uuids_by_key = defaultdict(set)
    catalog_queries_by_key = defaultdict(set)
    academy_uuids_by_key = defaultdict(set)
    academy_tags_by_key = defaultdict(set)
    video_ids_by_key = defaultdict(set)

    catalog_query_uuid_by_catalog_uuid = defaultdict(set)
    customer_uuid_by_catalog_uuid = defaultdict(set)
    academy_uuids_by_catalog_uuid = defaultdict(set)
    academy_tags_by_catalog_uuid = defaultdict(set)

    # Create a shared convenience queryset to prefetch catalogs for all metadata lookups below.
    all_catalog_queries = CatalogQuery.objects.prefetch_related(
        'enterprise_catalogs',
        'enterprise_catalogs__academies',
        'enterprise_catalogs__academies__tags',
        'enterprise_catalogs__academies__tags__content_metadata',
    )

    # Retrieve ContentMetadata records for:
    # * Course runs, courses, programs and learner pathways that are directly requested, and
    # * Courses and programs indirectly related to something directly requested.
    #   - e.g. A course that was not directly requested, but is a member of a program which was requested.
    #   - e.g. A program that was not directly requested, but is a member of a pathway which was requested.
    content_metadata_no_courseruns = ContentMetadata.objects.filter(
        # All content (courses, course runs, programs, pathways) directly requested.
        Q(content_key__in=content_keys_batch)
        # All course runs, courses, or programs contained in programs or pathways requested.  In order to collect all
        # UUIDs for a given program or pathway, all containing objects are needed too, but those may not happen to be
        # part of the current batch.
        # This could include non-indexable content, so they will need to be filtered out next.
        | Q(
            content_type__in=[COURSE_RUN, COURSE, PROGRAM],
            associated_content_metadata__content_type__in=[PROGRAM, LEARNER_PATHWAY],
            associated_content_metadata__content_key__in=content_keys_batch,
        )
    ).prefetch_related(
        Prefetch('catalog_queries', queryset=all_catalog_queries),
    )
    if getattr(settings, 'SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS', False):
        # Make the courses that we index actually contain restricted runs in the payload.
        content_metadata_no_courseruns = content_metadata_no_courseruns.prefetch_restricted_overrides()
        # Also just prefetch the rest of the restricted courses which will
        # allow us to find all catalog_queries explicitly allowing a restricted
        # run for each course.
        content_metadata_no_courseruns = content_metadata_no_courseruns.prefetch_related(
            'restricted_courses__catalog_query'
        )
    # Perform filtering of non-indexable objects in-memory because the list may be too long to shove into a SQL query.
    content_metadata_no_courseruns = [
        cm for cm in content_metadata_no_courseruns
        if cm.content_key in all_indexable_content_keys
    ]

    # Retrieve ContentMetadata records for any course run which is part of any course found in the previous query.
    course_content_keys = [cm.content_key for cm in content_metadata_no_courseruns]
    content_metadata_courseruns = ContentMetadata.objects.filter(
        parent_content_key__in=course_content_keys
    ).prefetch_related(
        Prefetch('catalog_queries', queryset=all_catalog_queries),
    )
    course_run_content_keys = [cm.content_key for cm in content_metadata_courseruns]
    videos = Video.objects.filter(
        parent_content_metadata__content_key__in=course_run_content_keys
    ).select_related('parent_content_metadata')

    # Combine both querysets to represent all the ContentMetadata needed to process this batch.
    #
    # DEFICIENCY: This final set does not guarantee inclusion of courses (or course runs) indirectly related to a
    # requested to a pathway via an association chain of course->program->pathway.  This maybe should be added!  When it
    # is added, a related change must be made in the third pass (below) to chain
    # `pathway_to_programs_courses_mapping` and `program_to_courses_mapping` to actually collect the UUIDs.
    content_metadata_to_process = content_metadata_no_courseruns + list(content_metadata_courseruns)

    # First pass over the batch of content.  The goal for this pass is to collect all the UUIDs directly associated with
    # each content.  This DOES NOT capture any UUIDs indirectly related to programs or pathways via associated courses
    # or programs.
    for metadata in content_metadata_to_process:  # pylint: disable=too-many-nested-blocks
        if metadata.content_type in (COURSE, PROGRAM, LEARNER_PATHWAY):
            content_key = metadata.content_key
        else:
            # Course runs should contribute their UUIDs to the parent course.
            content_key = metadata.parent_content_key
        associated_catalog_queries = metadata.catalog_queries.all()
        if metadata.content_type == COURSE and getattr(settings, 'SHOULD_INDEX_COURSES_WITH_RESTRICTED_RUNS', False):
            # "unicorn" courses (i.e. courses with only restricted runs) should only be indexed for
            # catalog queries that explicitly allow runs in those courses. We can tell that a course
            # has only restricted runs simply by checking that it normally doesn't have an
            # advertised run. "Normally" means checking the `_json_metadata` attribute instead of
            # `json_metadata`.
            # pylint: disable=protected-access
            is_unrestricted_course_advertised = bool(metadata._json_metadata.get('advertised_course_run_uuid'))
            if not is_unrestricted_course_advertised:
                associated_catalog_queries = (
                    rc.catalog_query for rc in metadata.restricted_courses.exclude(catalog_query=None)
                )
        for video in videos:
            if (metadata.content_type == COURSE_RUN
                    and video.parent_content_metadata.content_key == metadata.content_key):
                video_ids_by_key[content_key].add(str(video.edx_video_id))
        for catalog_query in associated_catalog_queries:
            catalog_queries_by_key[content_key].add((str(catalog_query.uuid), catalog_query.title))
            # This line is possible thanks to `all_catalog_queries` with the prefectch_related() above.
            associated_catalogs = catalog_query.enterprise_catalogs.all()
            for catalog in associated_catalogs:
                catalog_uuids_by_key[content_key].add(str(catalog.uuid))
                customer_uuids_by_key[content_key].add(str(catalog.enterprise_uuid))
                # Cache UUIDs related to each catalog.
                catalog_query_uuid_by_catalog_uuid[str(catalog.uuid)].add(
                    (str(catalog_query.uuid), catalog_query.title)
                )
                customer_uuid_by_catalog_uuid[str(catalog.uuid)].add(str(catalog.enterprise_uuid))
                associated_academies = catalog.academies.all()
                for academy in associated_academies:
                    associated_academy_tags = academy.tags.all()
                    academy_uuids_by_key[content_key].add(str(academy.uuid))
                    academy_uuids_by_catalog_uuid[str(catalog.uuid)].add(str(academy.uuid))
                    for tag in associated_academy_tags:
                        if tag.content_metadata.filter(content_key=content_key):
                            academy_tags_by_key[content_key].add(str(tag.title))
                            academy_tags_by_catalog_uuid[str(catalog.uuid)].add(str(tag.title))

    # Second pass.  This time the goal is to capture indirect relationships on programs:
    #  * For each program:
    #    - Absorb all UUIDs associated with every associated course.
    for program_metadata in content_metadata_to_process:
        if program_metadata.content_type != PROGRAM:
            continue
        program_content_key = program_metadata.content_key
        # Create a list of lists of catalog UUIDs, each sub-list representing the catalog UUIDs for one course of
        # the program. Note: since this loops over ALL courses of a program, it may encounter a non-indexable
        # course; for these courses, we will not find any catalogs and contribute an empty sub-list. The end result
        # is that if a program contains any non-indexable content, no common catalogs will be found.
        catalog_uuids_for_all_courses_of_program = [
            catalog_uuids_by_key[course_metadata.content_key]
            for course_metadata in program_to_courses_mapping[program_content_key]
        ]
        common_catalogs = set()
        if catalog_uuids_for_all_courses_of_program:
            common_catalogs = set.intersection(*catalog_uuids_for_all_courses_of_program)
            catalog_uuids_by_key[program_content_key].update(common_catalogs)
            for catalog_uuid in common_catalogs:
                catalog_queries_by_key[program_content_key].update(
                    catalog_query_uuid_by_catalog_uuid[catalog_uuid]
                )
                customer_uuids_by_key[program_content_key].update(
                    customer_uuid_by_catalog_uuid[catalog_uuid]
                )
                academy_uuids_by_key[program_content_key].update(
                    academy_uuids_by_catalog_uuid[catalog_uuid]
                )
                academy_tags_by_key[program_content_key].update(
                    academy_tags_by_catalog_uuid[catalog_uuid]
                )

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
            academy_uuids_by_key[pathway_content_key].update(academy_uuids_by_key[metadata.content_key])
            academy_tags_by_key[pathway_content_key].update(academy_tags_by_key[metadata.content_key])

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
            academy_uuids_by_key[metadata.content_key],
            academy_tags_by_key[metadata.content_key],
            video_ids_by_key[metadata.content_key],
        )

        num_content_metadata_indexed += 1

    for video in videos:
        add_video_to_algolia_objects(
            video,
            algolia_products_by_object_id,
            customer_uuids_by_key[video.parent_content_metadata.parent_content_key],
            catalog_uuids_by_key[video.parent_content_metadata.parent_content_key],
            catalog_queries_by_key[video.parent_content_metadata.parent_content_key],
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
        f'{len(content_metadata_to_process)} content metadata found, '
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
    # Convert the content_keys list into a set that only takes O(1) on average to lookup.
    all_content_keys_set = set(content_keys)
    # Produce a generator of batches of algolia products to index.  Each batch has an unpredictable, variable length.
    # Not immediately evaluated, so no memory is consumed yet.
    algolia_products_batch_generator = (
        _get_algolia_products_for_batch(
            batch_num,
            content_keys_batch,
            all_content_keys_set,
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
    # this library function will chunk the iterable again using a default batch size of 1000.
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


@shared_task(base=LoggedTaskWithRetry, bind=True)
@expiring_task_semaphore()
def update_catalog_metadata_task(self, catalog_query_id, force=False, dry_run=False):  # pylint: disable=unused-argument
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
        associated_content_keys = update_contentmetadata_from_discovery(catalog_query, dry_run)
    except Exception as e:
        logger.exception(
            f'Something went wrong while updating content metadata from discovery using catalog: {catalog_query_id} '
            f'after update_catalog_metadata_task_seconds={time.perf_counter() - start_time} seconds',
            exc_info=e,
        )
        raise e
    logger.info(
        f'Finished update_catalog_metadata_task with {len(associated_content_keys)} '
        f'associated content keys for catalog {catalog_query_id} '
        f'after update_catalog_metadata_task_seconds={time.perf_counter() - start_time} seconds'
    )


@shared_task(base=LoggedTaskWithRetry, bind=True)
@expiring_task_semaphore()
def fetch_missing_course_metadata_task(self, force=False, dry_run=False):  # pylint: disable=unused-argument
    """
    Creates a CatalogQuery for all the courses that do not have ContentMetadata instance.

    After creating the catalog query it calls update_contentmetadata_from_discovery to update the metadata for these
    courses. Course metadata is only missing for program courses so the initial query only looks for course metadata
    that are embedded inside a program.
    """
    logger.info('[FETCH_MISSING_METADATA] fetch_missing_course_metadata_task task started.')
    program_metadata_list = ContentMetadata.objects.filter(
        content_type=PROGRAM
    ).values_list(
        '_json_metadata',
        flat=True,
    )
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

        associated_content_keys = update_contentmetadata_from_discovery(catalog_query, dry_run)
        logger.info('[FETCH_MISSING_METADATA] Finished fetch_missing_course_metadata_task with {} associated content '
                    'keys for catalog {}'.format(len(associated_content_keys), catalog_query.id))
    else:
        logger.info('[FETCH_MISSING_METADATA] No missing key found in fetch_missing_course_metadata_task')


@shared_task(base=LoggedTaskWithRetry, bind=True)
@expiring_task_semaphore()
def fetch_missing_pathway_metadata_task(self, force=False, dry_run=False):  # pylint: disable=unused-argument
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
    associated_content_keys = update_contentmetadata_from_discovery(catalog_query, dry_run)
    logger.info(
        '[FETCH_MISSING_METADATA] Finished Pathways fetch_missing_pathway_metadata_task with {} associated content '
        'keys for catalog {}'.format(
            len(associated_content_keys), catalog_query.id
        )
    )

    learner_pathway_metadata_list = ContentMetadata.objects.filter(content_type=LEARNER_PATHWAY).values_list(
        '_json_metadata', flat=True,
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

        associated_content_keys = update_contentmetadata_from_discovery(catalog_query, dry_run)
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

        associated_content_keys = update_contentmetadata_from_discovery(catalog_query, dry_run)
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
            if dry_run:
                logger.info(
                    ('[FETCH_MISSING_METADATA][Dry Run] Learner Pathway {} associations created.'
                        'No. of associations: {}').format(
                        pathway.content_key,
                        pathway.associated_content_metadata.count(),
                    )
                )
            else:
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
