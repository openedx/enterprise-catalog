import logging

from celery import group
from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import (
    fetch_missing_course_metadata_task,
    fetch_missing_pathway_metadata_task,
    update_catalog_metadata_task,
    update_full_content_metadata_task,
)
from enterprise_catalog.apps.catalog.constants import COURSE, TASK_TIMEOUT
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    CatalogUpdateCommandConfig,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Updates Content Metadata, along with the associations of Catalog Queries and Content Metadata.'
    )

    def _update_catalog_metadata_task(self, catalog_query, no_async, **kwargs):
        async_message = (
            'Spinning off update_catalog_metadata_task from update_content_metadata command'
            ' to update content_metadata for catalog query %s.'
        )
        if not no_async:
            logger.info(async_message, catalog_query)
        return update_catalog_metadata_task.s(catalog_query.id, **kwargs)

    def _fetch_missing_course_metadata_task_async(self, **kwargs):
        logger.info(
            'Spinning off fetch_missing_course_metadata_task from update_content_metadata command'
            ' to update content_metadata of missing courses.'
        )
        return fetch_missing_course_metadata_task.si(**kwargs).apply_async().get(
            timeout=TASK_TIMEOUT,
            propagate=True,
        )

    def _fetch_missing_pathway_metadata_task_async(self, **kwargs):
        logger.info(
            'Spinning off fetch_missing_pathway_metadata_task from update_content_metadata command'
            ' to update content_metadata of missing pathways.'
        )
        return fetch_missing_pathway_metadata_task.si(**kwargs).apply_async().get(
            timeout=TASK_TIMEOUT,
            propagate=True,
        )

    def _update_full_content_metadata_task_async(self, **kwargs):
        """
        Returns a task signature for the `update_full_content_metadata_task`.

        Note that the keys get filtered down to course content keys inside the task.
        """
        message = (
            'Spinning off update_full_content_metadata_task from update_content_metadata command'
            ' to replace minimal json_metadata from /search/all/ with full json_metadata from /courses/.'
        )
        logger.info(message)

        # task.si() is used as a shortcut for an immutable signature to avoid calling this with the results from the
        # previously run `update_catalog_metadata_task`.
        # https://docs.celeryproject.org/en/master/userguide/canvas.html#immutability
        return update_full_content_metadata_task.si(**kwargs).apply_async().get(
            timeout=TASK_TIMEOUT,
            propagate=True,
        )

    def add_arguments(self, parser):
        # Argument to force execution of celery task, ignoring time since last execution
        parser.add_argument(
            '--force',
            default=False,
            action='store_true',
            help=(
                'Will read the value of this option from the CatalogUpdateCommandConfig table '
                'if a record is present and enabled.'
            ),
        )
        parser.add_argument(
            '--dry-run',
            dest='dry_run',
            default=False,
            action='store_true',
            help='Generate algolia products to index, but do not actually send them to algolia for indexing.',
        )
        parser.add_argument(
            '--no-async',
            dest='no_async',
            default=False,
            action='store_true',
            help='Run the task synchronously (without celery).',
        )

    def handle(self, *args, **options):
        """
        Runs a group of `update_catalog_metadata_tasks`, followed by
        a single `update_full_content_metadata_task` instance.
        """
        options.update(CatalogUpdateCommandConfig.current_options())

        no_async = options.get('no_async', False)
        flags = {k: options.get(k, False) for k in ('force', 'dry_run')}
        # Fetch metadata for the courses/programs that are missing.
        if no_async:
            fetch_missing_pathway_metadata_task.apply(kwargs=flags)
            fetch_missing_course_metadata_task.apply(kwargs=flags)
        else:
            self._fetch_missing_pathway_metadata_task_async(**flags)
            self._fetch_missing_course_metadata_task_async(**flags)

        # find all CatalogQuery records used by at least one EnterpriseCatalog to avoid
        # calling /search/all/ for a CatalogQuery that is not currently used by any catalogs.
        catalog_queries = CatalogQuery.objects.filter(enterprise_catalogs__isnull=False).distinct()

        if not catalog_queries:
            logger.error('No matching CatalogQuery objects found. Exiting.')
            return

        # First, we create a group of celery tasks that run in parallel to create/update ContentMetadata records
        # and associate those with the appropriate CatalogQuery(s).
        # It's possible that one of the tasks in the group will fail with a TaskRecentlyRunError.
        # Note that a failed task in a group does not stop the rest of the tasks in the group from running.
        # We consider this error innocuous, and don't want an occurrence(s) of it to prevent
        # update_full_content_metadata_task from being run.
        # Thus we run the update_catalog_metadata_tasks in their own group, wait
        # for the entire group to finish, and then execute update_full_content_metadata_task
        # asynchronously.  This is functionally equivalent to building a celery chord from this entire set of tasks.
        # We use this strategy instead because celery.chord() won't execute the trailing task if a failure occurs
        # in the set of parent tasks.
        # https://docs.celeryproject.org/en/v5.0.5/userguide/canvas.html
        update_group = group(
            [
                self._update_catalog_metadata_task(catalog_query, no_async, **flags)
                for catalog_query in catalog_queries
            ]
        )
        try:
            if no_async:
                update_group_result = update_group.apply(kwargs=flags)
            else:
                update_group_result = update_group.apply_async().get(
                    timeout=TASK_TIMEOUT,
                    propagate=True,
                )
            logger.info(
                'Finished doing catalog metadata update related to {} CatalogQueries'.format(len(update_group_result))
            )
        except Exception as exc:  # pylint: disable=broad-except
            # celery weirdly hijacks and prefixes the path of the below Exception
            # with `celery.backends.base` when it's raised.
            # So this block still catches only a specific error, just in a roundabout way.
            # This type of error shouldn't fail the whole command.
            # Subtasks of a celery group may fail without affecting/blocking the other subtasks
            # from running/succeeding.
            # Note that a GroupResult.get() will surface only the first instance
            # of an error, though other errors may occur.
            if type(exc).__name__ != 'TaskRecentlyRunError':
                raise
            else:
                logger.info(
                    'One or more update_catalog_metadata_task was recently run prior to this command, '
                    'and those particular tasks were thus skipped during the execution of this command.'
                )

        try:
            if no_async:
                update_full_content_metadata_task.apply(kwargs=flags)
            else:
                self._update_full_content_metadata_task_async(**flags)
            logger.info('Finished doing full update of metadata records.')
        except Exception as exc:
            # See comment above about celery exception prefixes.
            if type(exc).__name__ != 'TaskRecentlyRunError':
                raise
            else:
                logger.info(
                    'update_full_content_metadata_task was recently run prior to this command, '
                    'and was thus skipped during the execution of this command.'
                )
