from django.utils.decorators import method_decorator
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST

from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.export_utils import (
    querydict_to_dict,
    validate_query_facets,
)
from enterprise_catalog.apps.catalog.algolia_utils import (
    get_initialized_algolia_client,
)


class DefaultCatalogResultsView(GenericAPIView):
    """
    View to retrieve the top four Algolia results from a specified catalog.

    The endpoint will either fetch program or course data depending on a specified `content_type` param and defaults to
    courses if a content type isn't provided.
    """
    permission_classes = []
    valid_facets = ['enterprise_catalog_query_titles', 'content_type']

    algolia_attributes_to_retrieve = [
        'title',
        'key',
        'content_type',
        'partners',
        'advertised_course_run',
        'programs',
        'program_titles',
        'level_type',
        'language',
        'short_description',
        'subjects',
        'aggregation_key',
        'skills',
        'skill_names',
        'first_enrollable_paid_seat_price',
        'marketing_url',
        'upcoming_course_runs',
        'type',
        'recent_enrollment_count',
        'original_image_url',
        'full_description',
        'enterprise_catalog_query_uuids',
        'enterprise_catalog_query_titles',
        'card_image_url',
        'availability',
        'program_type',
        'course_keys',
        'authoring_organizations',
    ]

    def get_queryset(self, **kwargs):
        # Since this view does not hit any models, override the queryset
        pass

    @method_decorator(require_at_least_one_query_parameter('enterprise_catalog_query_titles'))
    @action(detail=True)
    def get(self, request, **kwargs):
        """
        GET entry point for the `DefaultCatalogResultsView`
        """
        facets = querydict_to_dict(request.query_params)
        invalid_facets = validate_query_facets(facets)

        learning_type = facets.get("learning_type", ['course'])[0]
        learning_type_v2 = facets.get("learning_type_v2", [None])[0]

        if invalid_facets:
            return Response({'Error': f'invalid facet(s): {invalid_facets} provided.'}, status=HTTP_400_BAD_REQUEST)

        catalog_filter = [
            f'enterprise_catalog_query_titles:{facets.get("enterprise_catalog_query_titles")[0]}',
            f'learning_type:{learning_type}'
        ]

        if learning_type_v2:
            catalog_filter.append(f'learning_type_v2:{learning_type_v2}')

        search_options = {
            'facetFilters': catalog_filter,
            'attributesToRetrieve': self.algolia_attributes_to_retrieve,
            'hitsPerPage': 4,
            'page': 0,
        }
        # algolia to search
        algolia_client = get_initialized_algolia_client()
        page = algolia_client.algolia_index.search('', search_options)
        return Response({'default_content': page.get('hits')}, status=HTTP_200_OK)
