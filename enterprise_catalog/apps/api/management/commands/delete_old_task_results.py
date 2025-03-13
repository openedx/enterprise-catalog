"""
Deletes TaskResult records older than some number of days in the past.
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_celery_results.models import TaskResult


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Deletes TaskResult records that were created more than some maximum number of days.'

    def add_arguments(self, parser):
        """
        Entry point to add arguments.
        """
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            default=False,
            help='Dry Run, print log messages without spawning the celery tasks.',
        )
        parser.add_argument(
            '--max-age-days',
            dest='max_age_days',
            type=int,
            default=365,
            help='The max age allowed for TaskResults to not be deleted',
        )

    def handle(self, *args, **options):
        is_dry_run = options['dry_run']
        max_age_days = options['max_age_days']

        cutoff = timezone.now() - timedelta(days=max_age_days)
        record_count = TaskResult.objects.filter(date_created__lt=cutoff).count()

        if is_dry_run:
            logger.info('DRY RUN: cutoff is %s, count to be deleted is %s', cutoff, record_count)
        else:
            logger.info('Deleting %s records older than %s', record_count, cutoff)
            TaskResult.objects.filter(date_created__lt=cutoff).delete()
            logger.info('Deletion succeeded')
