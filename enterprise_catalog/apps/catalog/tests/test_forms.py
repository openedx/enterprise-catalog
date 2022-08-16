import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.forms import CatalogQueryForm
from enterprise_catalog.apps.catalog.tests import factories


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

    def test_clean_content_filter(self):
        # Test the create case, where the form instance has no PK
        content_filter = {'key': ['coursev1:course1', 'coursev1:course2']}
        factories.CatalogQueryFactory.create(
            content_filter=content_filter,
        )
        form = CatalogQueryForm(data={'content_filter': content_filter})
        self.assertFalse(form.is_valid())

        # Test the update case, where the form instance will have a PK
        other_query = factories.CatalogQueryFactory.create(
            content_filter={'key': ['coursev1:course1', 'coursev1:cours55']}
        )
        form = CatalogQueryForm(instance=other_query, data={'content_filter': content_filter})
        self.assertFalse(form.is_valid())
