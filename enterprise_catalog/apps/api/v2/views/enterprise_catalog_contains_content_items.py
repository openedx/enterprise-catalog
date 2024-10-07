"""
"""
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.decorators import action
from rest_framework.response import Response

from enterprise_catalog.apps.api.constants import (
    CONTAINS_CONTENT_ITEMS_VIEW_CACHE_TIMEOUT_SECONDS,
)
from enterprise_catalog.apps.api.v1.decorators import (
    require_at_least_one_query_parameter,
)
from enterprise_catalog.apps.api.v1.utils import unquote_course_keys
from enterprise_catalog.apps.api.v1.views.enterprise_catalog_contains_content_items import (
    EnterpriseCatalogContainsContentItems,
)


class EnterpriseCatalogContainsContentItemsV2(EnterpriseCatalogContainsContentItems):
    """
    View to determine if an enterprise catalog contains certain content
    """
    @method_decorator(cache_page(CONTAINS_CONTENT_ITEMS_VIEW_CACHE_TIMEOUT_SECONDS))
    @method_decorator(require_at_least_one_query_parameter('course_run_ids', 'program_uuids'))
    @action(detail=True)
    def contains_content_items(self, request, uuid, course_run_ids, program_uuids, **kwargs):  # pylint: disable=unused-argument
        """
        Returns whether or not the EnterpriseCatalog contains the specified content.

        Multiple course_run_ids and/or program_uuids query parameters can be sent to this view to check for their
        existence in the specified enterprise catalog.
        """
        course_run_ids = unquote_course_keys(course_run_ids)

        enterprise_catalog = self.get_object()
        contains_content_items = enterprise_catalog.contains_content_keys(
            course_run_ids + program_uuids,
            include_restricted=True,
        )
        return Response({'contains_content_items': contains_content_items})
