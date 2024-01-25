"""
Management command for making instances of models with test factories.
"""

from edx_django_utils.data_generation.management.commands.manufacture_data import \
    Command as BaseCommand

from enterprise_catalog.apps.academy.tests.factories import *
from enterprise_catalog.apps.catalog.tests.factories import *
from enterprise_catalog.apps.curation.tests.factories import *


class Command(BaseCommand):
    """
    Management command for generating Django records from factories with custom attributes

    Example usage:
        $ ./manage.py manufacture_data --model enterprise_catalog.apps.catalog.models.EnterpriseCatalog /
            -title "Test Catalog"
    """
