import logging
from uuid import UUID

from edx_rbac.decorators import permission_required
from edx_rbac.mixins import PermissionRequiredForListingMixin
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ParseError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
)
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.v1.pagination import (
    PageNumberWithSizePagination,
)
from enterprise_catalog.apps.api.v1.serializers import (
    ContentMetadataSerializer,
    EnterpriseCurationConfigSerializer,
    HighlightSetSerializer,
)
from enterprise_catalog.apps.api.v1.views.base import BaseViewSet
from enterprise_catalog.apps.api.v1.views.curation import utils
from enterprise_catalog.apps.catalog.constants import (
    ENTERPRISE_CATALOG_ADMIN_ROLE,
    ENTERPRISE_CATALOG_LEARNER_ROLE,
    PERMISSION_HAS_ADMIN_ACCESS,
    PERMISSION_HAS_LEARNER_ACCESS,
)
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    EnterpriseCatalogRoleAssignment,
)
from enterprise_catalog.apps.catalog.rules import (
    enterprises_with_admin_access,
    has_access_to_all_enterprises,
)
from enterprise_catalog.apps.curation.models import (
    EnterpriseCurationConfig,
    HighlightedContent,
    HighlightSet,
)


logger = logging.getLogger(__name__)


class EnterpriseCurationConfigBaseViewSet(PermissionRequiredForListingMixin, BaseViewSet):
    """ Base viewset for common behavior for listing and retrieving EnterpriseCurationConfigs """
    renderer_classes = [JSONRenderer, XMLRenderer]
    serializer_class = EnterpriseCurationConfigSerializer
    lookup_field = 'uuid'

    # Fields required for controlling access in the `list()` action
    list_lookup_field = 'enterprise_uuid'
    role_assignment_class = EnterpriseCatalogRoleAssignment

    @property
    def requested_enterprise_uuid(self):
        if self.request_action == 'create':
            return utils.get_enterprise_uuid_from_request_data(self.request)
        return utils.get_enterprise_uuid_from_request_query_params(self.request)

    @property
    def requested_enterprise_curation_config_uuid(self):
        return self.kwargs.get('uuid')

    def get_permission_object(self):
        """
        Used for "retrieve" actions. Determines the context (enterprise UUID) to check
        against for role-based permissions.

        This object is passed to the rule predicate(s).
        """
        if self.requested_enterprise_uuid:
            return str(self.requested_enterprise_uuid)

        try:
            enterprise_curation_config = EnterpriseCurationConfig.objects.get(uuid=self.requested_enterprise_curation_config_uuid)
            return str(enterprise_curation_config.enterprise_uuid)
        except EnterpriseCurationConfig.DoesNotExist:
            return None

    @property
    def base_queryset(self):
        """
        Required by the `PermissionRequiredForListingMixin`.
        For non-list actions, this is what's returned by `get_queryset()`.
        For list actions, some non-strict subset of this is what's returned by `get_queryset()`.
        """
        kwargs = {}
        if self.requested_enterprise_uuid:
            kwargs.update({'enterprise_uuid': self.requested_enterprise_uuid})
        if self.requested_enterprise_curation_config_uuid:
            kwargs.update({'uuid': self.requested_enterprise_curation_config_uuid})
        return EnterpriseCurationConfig.objects.filter(**kwargs).prefetch_related(
            'catalog_highlights',
            'catalog_highlights__highlighted_content',
        ).order_by('-created')


class EnterpriseCurationConfigReadOnlyViewSet(EnterpriseCurationConfigBaseViewSet, viewsets.ReadOnlyModelViewSet):
    """ Viewset for listing and retrieving EnterpriseCurationConfigs. """
    permission_required = PERMISSION_HAS_LEARNER_ACCESS

    # Fields required for controlling access in the `list()` action
    allowed_roles = [ENTERPRISE_CATALOG_LEARNER_ROLE, ENTERPRISE_CATALOG_ADMIN_ROLE]


class EnterpriseCurationConfigViewSet(EnterpriseCurationConfigBaseViewSet, viewsets.ModelViewSet):
    """ Viewset for listing, retrieving, creating, and updating EnterpriseCurationConfigs. """
    permission_required = PERMISSION_HAS_ADMIN_ACCESS

    # Fields required for controlling access in the `list()` action
    allowed_roles = [ENTERPRISE_CATALOG_ADMIN_ROLE]

    def create(self, request, *args, **kwargs):
        """ Create a new EnterpriseCurationConfig """
        if not self.requested_enterprise_uuid:
            return Response(
                f'An enterprise UUID was not specified.',
                status=HTTP_400_BAD_REQUEST
            )

        try:
            existing_curation_config_for_enterprise = EnterpriseCurationConfig.objects.get(enterprise_uuid=self.requested_enterprise_uuid)
        except EnterpriseCurationConfig.DoesNotExist:
            existing_curation_config_for_enterprise = None

        if existing_curation_config_for_enterprise:
            return Response(
                f'An EnterpriseCurationConfig already exists for enterprise UUID {self.requested_enterprise_uuid}',
                status=HTTP_400_BAD_REQUEST
            )

        return super().create(request, *args, **kwargs)


class HighlightSetBaseViewSet(PermissionRequiredForListingMixin, BaseViewSet):
    """ Base viewset for listing, retrieving, creating, and updating HighlightSets """
    renderer_classes = [JSONRenderer, XMLRenderer]
    serializer_class = HighlightSetSerializer
    lookup_field = 'uuid'

    # Fields required for controlling access in the `list()` action
    list_lookup_field = 'enterprise_curation__enterprise_uuid'
    role_assignment_class = EnterpriseCatalogRoleAssignment

    @property
    def requested_enterprise_uuid(self):
        if self.request_action == 'create':
            return utils.get_enterprise_uuid_from_request_data(self.request)
        return utils.get_enterprise_uuid_from_request_query_params(self.request)

    @property
    def requested_highlight_set_uuid(self):
        return self.kwargs.get('uuid')

    @property
    def requested_content_keys(self):
        return utils.get_content_keys_from_request_data(self.request)

    def get_permission_object(self):
        """
        Used for "retrieve" actions. Determines the context (enterprise UUID) to check
        against for role-based permissions.

        This object is passed to the rule predicate(s).
        """
        if self.requested_enterprise_uuid:
            return str(self.requested_enterprise_uuid)

        try:
            highlight_set = HighlightSet.objects.get(uuid=self.requested_highlight_set_uuid)
            return str(highlight_set.enterprise_curation.enterprise_uuid)
        except HighlightSet.DoesNotExist:
            return None

    @property
    def base_queryset(self):
        """
        Required by the `PermissionRequiredForListingMixin`.
        For non-list actions, this is what's returned by `get_queryset()`.
        For list actions, some non-strict subset of this is what's returned by `get_queryset()`.
        """
        kwargs = {}
        if self.requested_enterprise_uuid:
            kwargs.update({'enterprise_curation__enterprise_uuid': self.requested_enterprise_uuid})
        if self.requested_highlight_set_uuid:
            kwargs.update({'uuid': self.requested_highlight_set_uuid})
        return HighlightSet.objects.filter(**kwargs).prefetch_related(
            'enterprise_curation',
            'highlighted_content',
        ).order_by('-created')


class HighlightSetReadOnlyViewSet(HighlightSetBaseViewSet, viewsets.ReadOnlyModelViewSet):
    """ Viewset for listing and retrieving HighlightSets. """
    permission_required = PERMISSION_HAS_LEARNER_ACCESS

    # Fields required for controlling access in the `list()` action
    allowed_roles = [ENTERPRISE_CATALOG_LEARNER_ROLE, ENTERPRISE_CATALOG_ADMIN_ROLE]


class HighlightSetViewSet(HighlightSetBaseViewSet, viewsets.ModelViewSet):
    """
    Viewset for creating, updating, listing and retrieving HighlightSets.
    """
    permission_required = PERMISSION_HAS_ADMIN_ACCESS

    # Fields required for controlling access in the `list()` action
    allowed_roles = [ENTERPRISE_CATALOG_ADMIN_ROLE]

    def _validate_existing_enterprise_curation_config(self):
        """
        Validates whether there is an existing EnterpriseCurationConfig object associated with
        the requested enterprise UUID.
        """
        try:
            existing_curation_config_for_enterprise = EnterpriseCurationConfig.objects.get(enterprise_uuid=self.requested_enterprise_uuid)
        except EnterpriseCurationConfig.DoesNotExist:
            existing_curation_config_for_enterprise = None

        return existing_curation_config_for_enterprise

    def create(self, request, *args, **kwargs):
        """ Create a new HighlightSet """
        if not self.requested_enterprise_uuid:
            return Response(
                f'An enterprise UUID was not specified.',
                status=HTTP_400_BAD_REQUEST
            )

        curation_config = self._validate_existing_enterprise_curation_config()
        if not curation_config:
            return Response(
                f'An EnterpriseCurationConfig must exist for enterprise UUID {self.requested_enterprise_uuid} '
                'in order to create a HighlightSet',
                status=HTTP_400_BAD_REQUEST
            )
        request.data['enterprise_curation'] = str(curation_config.uuid)

        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='add-content')
    def add_content(self, request, uuid, *args, **kwargs):
        """ Add content to an existing HighlightSet """
        content_keys = set(utils.get_content_keys_from_request_data(request))
        highlighted_content = []
        ignored_content_keys = []
        added_content_keys = []
        existing_content_keys = []
        for content_key in content_keys:
            try:
                content_metadata = ContentMetadata.objects.get(content_key=content_key)
            except ContentMetadata.DoesNotExist:
                logger.warning('content_key not found: %s', str(content_key))
                ignored_content_keys.append(content_key)
                continue
            highlighted_content.append(content_metadata)

        highlight_set = HighlightSet.objects.get(uuid=uuid)

        for content_metadata_item in highlighted_content:
            __, created = HighlightedContent.objects.get_or_create(
                catalog_highlight_set=highlight_set,
                content_metadata=content_metadata_item,
            )
            if created:
                added_content_keys.append(content_metadata_item.content_key)
            else:
                existing_content_keys.append(content_metadata_item.content_key)

        return Response(
            {
                'ignored_content_keys': ignored_content_keys,
                'added_content_keys': added_content_keys,
                'existing_content_keys': existing_content_keys,
                'highlight_set': HighlightSetSerializer(highlight_set).data,
            },
            status=HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='remove-content')
    def remove_content(self, request, uuid, *args, **kwargs):
        """ Remove existing content from an existing HighlightSet """
        content_keys = set(utils.get_content_keys_from_request_data(request))
        removed_content_keys = set()

        highlight_set = HighlightSet.objects.get(uuid=uuid)
        existing_content = highlight_set.highlighted_content
        existing_content_to_remove = existing_content.filter(content_metadata__content_key__in=list(content_keys))
        if existing_content_to_remove:
            removed_content_keys.update([
                content_item.content_metadata.content_key
                for content_item in existing_content_to_remove
            ])
            existing_content_to_remove.delete()

        return Response(
            {
                'removed_content_keys': removed_content_keys,
                'ignored_content_keys': list(content_keys.difference(removed_content_keys)),
                'highlight_set': HighlightSetSerializer(highlight_set).data,
            },
            status=HTTP_201_CREATED,
        )
