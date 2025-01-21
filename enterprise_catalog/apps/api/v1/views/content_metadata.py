import uuid

from django.db.models import Q
from django.shortcuts import get_object_or_404
from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.v1.pagination import (
    PageNumberWithSizePagination,
)
from enterprise_catalog.apps.api.v1.serializers import ContentMetadataSerializer
from enterprise_catalog.apps.catalog.constants import COURSE_RUN
from enterprise_catalog.apps.catalog.models import ContentMetadata


# https://stackoverflow.com/questions/53847404/how-to-check-uuid-validity-in-python
def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False


# https://stackoverflow.com/questions/4578590/python-equivalent-of-filter-getting-two-output-lists-i-e-partition-of-a-list
def partition(pred, iterable):
    trues = []
    falses = []
    for item in iterable:
        if pred(item):
            trues.append(item)
        else:
            falses.append(item)
    return trues, falses


class ContentMetadataView(viewsets.ReadOnlyModelViewSet):
    """
    View for retrieving and listing base content metadata.
    """
    serializer_class = ContentMetadataSerializer
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [JSONRenderer, XMLRenderer]
    queryset = ContentMetadata.objects.all()
    pagination_class = PageNumberWithSizePagination

    @property
    def pk_is_object_id(self):
        return self.kwargs.get('pk', '').isdigit()

    @property
    def pk_is_content_uuid(self):
        return not self.pk_is_object_id and is_valid_uuid(self.kwargs.get('pk'))

    @property
    def pk_is_content_key(self):
        return not self.pk_is_object_id and not self.pk_is_content_uuid

    @property
    def coerce_to_parent_course(self):
        return self.request.query_params.get('coerce_to_parent_course', False)

    def get_queryset(self, **kwargs):
        """
        Returns all content metadata objects filtered by an optional request query param (LIST) ``content_identifiers``

        If ``?coerce_to_parent_course=true` is passed to the list endpoint, any course runs which
        would have been returned are coerced into their parent course in the response. No course
        runs are returned when this setting is true.
        """
        queryset = self.queryset

        # Find all directly requested content
        content_filters = self.request.query_params.getlist('content_identifiers')
        queryset_direct = None
        content_keys = []
        if content_filters:
            content_uuids, content_keys = partition(is_valid_uuid, content_filters)
            queryset_direct = self.queryset.filter(
                Q(content_uuid__in=content_uuids) | Q(content_key__in=content_keys)
            )
            queryset = queryset_direct

        # If ``?parent_course=true`` was passed, exclude course runs.
        if self.coerce_to_parent_course:
            query_filters = ~Q(content_type=COURSE_RUN)
            # If ``?content_identifiers=`` was passed, follow any matched course run objects back up
            # to their parent courses and include those in the response.
            if content_filters:
                parent_content_keys = list(
                    record[0] for record in
                    queryset_direct.filter(content_type=COURSE_RUN).values_list('parent_content_key')
                )
                all_content_keys_to_find = content_keys + parent_content_keys
                query_filters &= (
                    Q(content_uuid__in=content_uuids) | Q(content_key__in=all_content_keys_to_find)
                )
            queryset = self.queryset.filter(query_filters)

        return queryset

    def retrieve(self, request, *args, pk=None, **kwargs):
        """
        Override to support querying by content key/uuid, and to optionally coerce runs to courses.
        """
        # Support alternative pk types besisdes just the raw object IDs (which are completely opaque
        # to API clients).
        obj = None
        if self.pk_is_content_uuid:
            obj = get_object_or_404(self.queryset, content_uuid=pk)
        elif self.pk_is_content_key:
            obj = get_object_or_404(self.queryset, content_key=pk)
        else:
            obj = get_object_or_404(self.queryset, pk=pk)

        # Coerce course runs to courses if requested.
        if self.coerce_to_parent_course:
            if obj.content_type == COURSE_RUN:
                obj = get_object_or_404(self.queryset, content_key=obj.parent_content_key)

        # Finally, call super's retrieve() which has more DRF guts that are best not duplicated in
        # this codebase.
        self.kwargs['pk'] = obj.id
        return super().retrieve(request, *args, **kwargs)
