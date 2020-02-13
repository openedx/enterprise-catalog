""" Management command to run worker that will act on messages  """
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from kombu import Connection
from kombu.utils.debug import setup_logging

from enterprise_catalog.apps.catalog.consumers import CatalogConsumer


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Runs a worker to act on messages received from queue.
    """
    def handle(self, *args, **options):
        setup_logging(loglevel='DEBUG')

        with Connection(settings.BROKER_URL) as conn:
            try:
                CatalogConsumer(conn).run()
            except KeyboardInterrupt:
                print('bye bye')
