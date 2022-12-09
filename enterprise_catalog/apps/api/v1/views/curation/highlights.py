import logging
from uuid import UUID

from edx_django_utils.cache import RequestCache
from edx_rbac.decorators import permission_required
from edx_rbac.mixins import PermissionRequiredForListingMixin
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ParseError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
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


REQUEST_CACHE_NAMESPACE = 'CURATION_REQUEST_CACHE'
CONTENT_PER_HIGHLIGHTSET_LIMIT = 12
HIGHLIGHTSETS_PER_ENTERPRISE_LIMIT = 8
logger = logging.getLogger(__name__)


class LimitExceeded(Exception):
    """
    Use for any errors related to exceeding backend limits on object creation, such as maximum highlighted content per
    highlight set.
    """
    pass


class EnterpriseCurationConfigBaseViewSet(PermissionRequiredForListingMixin, BaseViewSet):
    """
    Base viewset for common behavior for listing and retrieving EnterpriseCurationConfigs
    """
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
            enterprise_curation_config = EnterpriseCurationConfig.objects.get(
                uuid=self.requested_enterprise_curation_config_uuid
            )
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
    """
    Viewset for listing and retrieving EnterpriseCurationConfigs.
    """
    permission_required = PERMISSION_HAS_LEARNER_ACCESS

    # Fields required for controlling access in the `list()` action
    allowed_roles = [ENTERPRISE_CATALOG_LEARNER_ROLE, ENTERPRISE_CATALOG_ADMIN_ROLE]


class EnterpriseCurationConfigViewSet(EnterpriseCurationConfigBaseViewSet, viewsets.ModelViewSet):
    """
    Viewset for listing, retrieving, creating, and updating EnterpriseCurationConfigs.
    """
    permission_required = PERMISSION_HAS_ADMIN_ACCESS

    # Fields required for controlling access in the `list()` action
    allowed_roles = [ENTERPRISE_CATALOG_ADMIN_ROLE]

    def create(self, request, *args, **kwargs):
        """
        Create a new EnterpriseCurationConfig
        """
        if not self.requested_enterprise_uuid:
            return Response(
                f'An enterprise UUID was not specified.',
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            existing_curation_config_for_enterprise = EnterpriseCurationConfig.objects.get(
                enterprise_uuid=self.requested_enterprise_uuid
            )
        except EnterpriseCurationConfig.DoesNotExist:
            existing_curation_config_for_enterprise = None

        if existing_curation_config_for_enterprise:
            return Response(
                f'An EnterpriseCurationConfig already exists for enterprise UUID {self.requested_enterprise_uuid}',
                status=status.HTTP_400_BAD_REQUEST
            )

        return super().create(request, *args, **kwargs)


class HighlightSetBaseViewSet(PermissionRequiredForListingMixin, BaseViewSet):
    """
    Base viewset for listing, retrieving, creating, and updating HighlightSets
    """
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
        """
        A cached list of content_keys from the `content_keys` attribute of the request body.

        TODO: Ideally, pull this nifty decorator (linked below) into edx-django-util so that more codebases other than
        edx-platform can use it, including this function which would otherwise be one line.
        https://github.com/edx/edx-platform/blob/2173a98ef8f5986ce6af9536b0ec2b2b413c818e/openedx/core/lib/cache_utils.py#L19
        """
        cache_key = 'requested_content_keys'

        # First, check the cache and return the requested_content_keys if found:
        request_cache = RequestCache(REQUEST_CACHE_NAMESPACE)
        cached_response = request_cache.get_cached_response(cache_key)
        if cached_response.is_found:
            return cached_response.value

        # Cache miss, so we need to calculate the requested_content_keys and store it:
        requested_content_keys = utils.get_content_keys_from_request_data(self.request)
        request_cache.set(cache_key, requested_content_keys)
        return requested_content_keys

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
    """
    Viewset for listing and retrieving HighlightSets.
    """
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
            existing_curation_config_for_enterprise = EnterpriseCurationConfig.objects.get(
                enterprise_uuid=self.requested_enterprise_uuid
            )
        except EnterpriseCurationConfig.DoesNotExist:
            existing_curation_config_for_enterprise = None

        return existing_curation_config_for_enterprise

    def _add_requested_content(self, highlight_set):
        """
        Helper function to add requested content to the given highlight set.

        Arguments:
            highlight_set (HighlightSet model instance): The highlight set to attempt to add content to.

        Returns:
            3-tuple of lists of str: Each tuple element represents "added", "ignored", and "existing" content_keys.
            Requested content keys are bucketed into one of those three lists.  "Ignored" content_keys are ones that
            don't exist in the catalog, and "existing" content_keys are ones that already exist inside the highlight
            set.

        Raises:
            LimitExceeded:
                If the requested content keys would cause the resulting highlight set to contain more than the maximum
                allowed content.
        """
        # Prepare the 3 output lists that collectively bucket all elements in the requested `content_keys` argument.
        added_content_keys = []  # requested content_keys that are successfully added as part of handling this request.
        ignored_content_keys = []  # requested content_keys that do not exist in the catalog.
        existing_content_keys = []  # requested content_keys that were already added in a previous request.

        # Determine `valid_requested_content_keys_to_add`.  Eventually equivalent to the union of `added_content_keys`
        # and `existing_content_keys`.  I.e. These are content_keys which are valid options to add to a highlight set.
        valid_requested_content_to_add = sorted(
            ContentMetadata.objects.filter(content_key__in=self.requested_content_keys),
            key=lambda cm: self.requested_content_keys.index(cm.content_key)
        )
        valid_requested_content_keys_to_add = [cm.content_key for cm in valid_requested_content_to_add]

        # Store the remainder in `ignored_content_keys`, representing content_keys that we will not even attempt to add.
        # Use a comprehension instead of set logic so that order is preserved.
        ignored_content_keys = [k for k in self.requested_content_keys if k not in valid_requested_content_keys_to_add]
        if ignored_content_keys:
            logger.warning('The following content_keys were not found: %s', ignored_content_keys)

        # Determine `all_prior_content_keys`, the content_keys already added to the highlight set prior to this request.
        # I.e. a superset of `existing_content_keys`.
        all_prior_highlighted_content = (
            HighlightedContent.objects
                              .filter(catalog_highlight_set=highlight_set)
                              .values('content_metadata__content_key')
        )
        all_prior_content_keys = [hc['content_metadata__content_key'] for hc in all_prior_highlighted_content]

        # Before actually creating the HighlightedContent objects, validate any limits that we want to impose.
        proposed_final_count = len(set(all_prior_content_keys).union(valid_requested_content_keys_to_add))
        if proposed_final_count > CONTENT_PER_HIGHLIGHTSET_LIMIT:
            raise LimitExceeded(
                f'Request exceeds the backend maximum content count per highlight set ({CONTENT_PER_HIGHLIGHTSET_LIMIT}).'
            )

        # Use a loop to create objects one-at-a-time instead of a single bulk create because we currently rely on each
        # object having sequential and unique `created` timestamps, used for output ordering.
        for content_metadata_item in valid_requested_content_to_add:
            __, created = HighlightedContent.objects.get_or_create(
                catalog_highlight_set=highlight_set,
                content_metadata=content_metadata_item,
            )
            if created:
                added_content_keys.append(content_metadata_item.content_key)
            else:
                existing_content_keys.append(content_metadata_item.content_key)

        return (added_content_keys, ignored_content_keys, existing_content_keys)

    def create(self, request, *args, **kwargs):
        """
        Create a new HighlightSet

        Arguments:
        - `request.data["enterprise_customer"]` (str): UUID of enterprise customer for which to create a highlight set.
        - `request.data["title"]` (str): Desired title of the highlight set.
        - `request.data["is_published"]` (bool, optional): True if the highlight set should be published.
        - `request.data["content_keys"]` (list of str, optional): A list of content keys to add.
        """
        if not self.requested_enterprise_uuid:
            return Response(
                f'An enterprise UUID was not specified.',
                status=status.HTTP_400_BAD_REQUEST
            )

        curation_config = self._validate_existing_enterprise_curation_config()
        if not curation_config:
            return Response(
                f'An EnterpriseCurationConfig must exist for enterprise UUID {self.requested_enterprise_uuid} '
                'in order to create a HighlightSet',
                status=status.HTTP_400_BAD_REQUEST
            )
        request.data['enterprise_curation'] = str(curation_config.uuid)

        # Validate that creating this HighlightSet would not cause the maximum number of highlight sets per enterprise
        # customer to be exceeded.
        existing_highlightset_count = len(HighlightSet.objects.filter(enterprise_curation=curation_config))
        if existing_highlightset_count == HIGHLIGHTSETS_PER_ENTERPRISE_LIMIT:
            return Response(
                'Request exceeds the backend maximum highlight set per enterprise customer '
                f'({HIGHLIGHTSETS_PER_ENTERPRISE_LIMIT}).',
                status=status.HTTP_403_FORBIDDEN
            )

        response = super().create(request, *args, **kwargs)

        # If the highlight set is created successfully, we can add requested content to it.
        if status.is_success(response.status_code) and self.requested_content_keys:
            highlight_set = HighlightSet.objects.get(uuid=response.data['uuid'])
            try:
                added_content_keys, ignored_content_keys, _ = self._add_requested_content(highlight_set)
            except LimitExceeded as e:
                return Response(str(e), status=status.HTTP_400_BAD_REQUEST)
            serializer = self.get_serializer(highlight_set)
            response_data = serializer.data
            response_data.update({'ignored_content_keys': ignored_content_keys})
            return Response(response_data, status=response.status_code, headers=response.headers)
        else:
            return response

    @action(detail=True, methods=['post'], url_path='add-content')
    def add_content(self, request, uuid, *args, **kwargs):
        """
        Add content to an existing HighlightSet

        Arguments:
        - `uuid` (str): UUID of the HighlightSet to add content to.
        - `request.data["content_keys"]` (list of str): A list of content keys to add.
        """
        highlight_set = HighlightSet.objects.get(uuid=uuid)
        try:
            added_content_keys, ignored_content_keys, existing_content_keys = self._add_requested_content(highlight_set)
        except LimitExceeded as e:
            return Response(str(e), status=status.HTTP_403_FORBIDDEN)
        return Response(
            {
                'ignored_content_keys': ignored_content_keys,
                'added_content_keys': added_content_keys,
                'existing_content_keys': existing_content_keys,
                'highlight_set': HighlightSetSerializer(highlight_set).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='remove-content')
    def remove_content(self, request, uuid, *args, **kwargs):
        """
        Remove existing content from an existing HighlightSet

        Arguments:
        - `uuid` (str): UUID of the HighlightSet to remove content from.
        - `request.data["content_keys"]` (str): A list of content keys to remove.
        """
        content_keys = self.requested_content_keys
        removed_content_keys = set()

        highlight_set = HighlightSet.objects.get(uuid=uuid)
        existing_content = highlight_set.highlighted_content
        existing_content_to_remove = existing_content.filter(content_metadata__content_key__in=content_keys)
        if existing_content_to_remove:
            removed_content_keys.update([
                content_item.content_metadata.content_key
                for content_item in existing_content_to_remove
            ])
            existing_content_to_remove.delete()

        return Response(
            {
                'removed_content_keys': removed_content_keys,
                'ignored_content_keys': list(set(content_keys).difference(removed_content_keys)),
                'highlight_set': HighlightSetSerializer(highlight_set).data,
            },
            status=status.HTTP_201_CREATED,
        )
