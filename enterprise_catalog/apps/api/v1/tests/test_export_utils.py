from django.test import TestCase

from enterprise_catalog.apps.api.v1 import export_utils
from enterprise_catalog.apps.catalog import algolia_utils


class ExportUtilsTests(TestCase):
    """
    Tests for the Enterprise Catalog API export utils
    """

    def test_retrieve_available_fields(self):
        """
        Test the export isn't retrieving fields which are not indexed
        """
        # assert that ALGOLIA_ATTRIBUTES_TO_RETRIEVE is a SUBSET of ALGOLIA_FIELDS
        assert set(export_utils.ALGOLIA_ATTRIBUTES_TO_RETRIEVE) <= set(algolia_utils.ALGOLIA_FIELDS)
