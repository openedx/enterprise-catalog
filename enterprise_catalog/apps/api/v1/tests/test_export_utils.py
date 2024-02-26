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

    def test_fetch_and_format_registration_date(self):
        """
        Test the export properly fetches executive education registration dates
        """
        # expected hit format from algolia, porperly reformatted for csv download
        assert export_utils.fetch_and_format_registration_date(
            {'end': '2002-02-15T12:12:200'}
        ) == '02-15-2002'
        # some other format from algolia, should return None
        assert export_utils.fetch_and_format_registration_date(
            {'end': '02-15-2015T12:12:200'}
        ) is None
