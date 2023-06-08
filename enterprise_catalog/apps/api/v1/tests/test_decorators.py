from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from rest_framework.exceptions import ValidationError

from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)


class DecoratorTests(TestCase):
    """
    Tests for the existence of at least one of the specified query in the decorator
    """

    def test_require_at_least_one_query_parameter(self):
        """
        Tests that at least one of the specified query parameters are included in the request
        """
        query_parameter_names = 'enterprise_catalog_query_titles'

        @require_at_least_one_query_parameter(query_parameter_names)
        def my_view(request):
            return HttpResponse('a response for request {}'.format(request))
        request = RequestFactory().get('/')
        request.query_params = request.GET

        with self.assertRaisesMessage(ValidationError,
                                      'You must provide at least one of the following '
                                      'query parameters: enterprise_catalog_query_titles.'):
            my_view(request)
