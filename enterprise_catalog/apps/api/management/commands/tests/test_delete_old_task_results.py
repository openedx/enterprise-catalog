"""
Tests the delete_old_task_results mgmt command.
"""
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from django_celery_results.models import TaskResult


class DeleteOldTaskResultsTests(TestCase):
    """
    Tests the delete_old_task_results mgmt command.
    """
    command_name = 'delete_old_task_results'

    def tearDown(self):
        super().tearDown()
        TaskResult.objects.all().delete()

    def _set_date_created(self, task, date_created):
        """
        TaskResult.date_created has auto_now_add=True, so we have to manually
        change the date after creation.
        """
        task.date_created = date_created
        task.save()

    def test_dry_run(self):
        """
        Tests that a dry-run doesn't actually delete any records.
        """
        task = TaskResult.objects.create(
            task_name='foo',
        )
        self._set_date_created(task, timezone.now() - timedelta(days=100000))
        call_command(self.command_name, dry_run=True)
        self.assertEqual(
            TaskResult.objects.all().count(),
            1,
        )

    def test_deletes_results_older_than_default(self):
        """
        Tests that we delete tasks older than 365 days if no max-age-days arg is provided.
        """
        task_1 = TaskResult.objects.create(task_id='1', task_name='foo')
        self._set_date_created(task_1, timezone.now() - timedelta(days=366))

        task_2 = TaskResult.objects.create(task_id='2', task_name='foo')
        self._set_date_created(task_2, timezone.now() - timedelta(days=364, hours=23, minutes=59))

        call_command(self.command_name)

        self.assertEqual(
            TaskResult.objects.all().count(),
            1,
        )
        with self.assertRaises(TaskResult.DoesNotExist):
            task_1.refresh_from_db()

    def test_deletes_results_with_max_age_days_arg(self):
        """
        Tests that we delete tasks older the number of days provided by the max-age-days arg.
        """
        task_1 = TaskResult.objects.create(task_id='1', task_name='foo')
        self._set_date_created(task_1, timezone.now() - timedelta(days=26))

        task_2 = TaskResult.objects.create(task_id='2', task_name='foo')
        self._set_date_created(task_2, timezone.now() - timedelta(days=24, hours=23, minutes=59))

        call_command(self.command_name, max_age_days=25)

        self.assertEqual(
            TaskResult.objects.all().count(),
            1,
        )
        with self.assertRaises(TaskResult.DoesNotExist):
            task_1.refresh_from_db()
