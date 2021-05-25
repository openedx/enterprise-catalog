import logging
from pprint import pprint

from django.core.management.base import BaseCommand
from django_celery_results.models import TaskResult

from enterprise_catalog.apps.api.tasks import (
    add_two_numbers,
    multiply_addition_results,
)


logger = logging.getLogger(__name__)


TASKS_BY_NAME = {
    task.name.split('.')[-1]: task
    for task in [add_two_numbers, multiply_addition_results]
}


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            'celery_task_name', nargs=1, help='The name of the celery task to run',
        )
        parser.add_argument(
            'celery_task_args', nargs='*', type=int, help='The arguments of the celery task',
        )
        parser.add_argument(
            '--log-results', action='store_true', default=False,
        )

    def handle(self, *args, **options):
        #import pdb; pdb.set_trace()
        celery_task = TASKS_BY_NAME.get(options['celery_task_name'][0])

        celery_result = celery_task.apply_async(args=options['celery_task_args'])
        logger.info('The task result is %r', celery_result.get())

        # This will output every TaskResult record for the requested task name
        if options['log_results']:
            for task_result_record in TaskResult.objects.filter(task_name=celery_task.name):
                logger.info(pprint(task_result_record.__dict__))
