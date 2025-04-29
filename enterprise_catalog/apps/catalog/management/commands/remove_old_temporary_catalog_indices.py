import logging

from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import (
    remove_old_temporary_catalog_indices_task,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Reindex course data in Algolia, adding on enterprise-specific metadata'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            default=False,
            action='store_true',
            help='Force execution of celery task, ignoring time since last execution.',
        )
        parser.add_argument(
            '--dry-run',
            dest='dry_run',
            action='store_true',
            default=False,
            help='List algolia indices to be removed, but do not actually remove them.',
        )
        parser.add_argument(
            '--min-days',
            dest='min_days',
            default=10,
            type=int,
            help='List algolia indices to be removed, but do not actually remove them.',
        )
        parser.add_argument(
            '--max-days',
            dest='max_days',
            default=60,
            type=int,
            help='List algolia indices to be removed, but do not actually remove them.',
        )

    def handle(self, *_args, **options):
        """
        Runs a celery task to remove leftover catalog `_tmp_` indices
        that have a creation date between 60 and 10 days ago.
        """
        try:
            force_task_execution = options.get('force', False)
            dry_run = options.get('dry_run', False)
            min_days = options.get('min_days', 10)
            max_days = options.get('max_days', 60)
            remove_old_temporary_catalog_indices_task.apply_async(
                kwargs={
                    'force': force_task_execution,
                    'dry_run': dry_run,
                    'min_days_ago': min_days,
                    'max_days_ago': max_days
                }
            )
            logger.info(
                'index_enterprise_catalog_in_algolia_task from command index_enterprise_catalog_in_algolia'
                'finished successfully.'
            )
        except Exception as exc:  # pylint: disable=broad-except
            # celery weirdly hijacks and prefixes the path of the below Exception
            # with `celery.backends.base` when it's raised.
            # So this block still catches only a specific error, just in a roundabout way.
            if type(exc).__name__ != 'TaskRecentlyRunError':
                raise
            else:
                logger.info(
                    'remove_old_temporary_catalog_indices_task was recently run prior to this command, '
                    'and was thus skipped during the execution of this command.'
                )
