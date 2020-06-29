import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.forms import CatalogQueryForm


@ddt.ddt
class TestCatalogQueryAdmin(TestCase):
    @ddt.data(
        ({'content_filter': {'key': 'coursev1:course1'}}, ["Content filter 'key' must be of type <class 'list'>"]),
        (
            {'content_filter': {'first_enrollable_paid_seat_price__lte': [12]}},
            ["Content filter 'first_enrollable_paid_seat_price__lte' must be of type <class 'str'>"]
        ),
        ({'content_filter': {'key': [3, 'course']}}, ["Content filter 'key' must contain values of type <class 'str'>"])
    )
    @ddt.unpack
    def test_catalog_query_form_failure(self, cfdata, error):
        form = CatalogQueryForm(data=cfdata)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['content_filter'], error)

    @ddt.data(
        ({'content_filter': {'key': ['coursev1:course1', 'coursev1:course2']}},),
        ({'content_filter': {'aggregation_key': ['courserun:course', 'courserun:course2']}},),
        ({'content_filter': {'first_enrollable_paid_seat_price__lte': '12'}},),
        ({'content_filter': {'key': ['coursev1:course1'], 'first_enrollable_paid_seat_price__lte': '50'}},)
    )
    @ddt.unpack
    def test_catalog_query_form_success(self, cfdata):
        form = CatalogQueryForm(data=cfdata)
        self.assertTrue(form.is_valid())
