import collections
from logging import getLogger
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils.translation import gettext as _
from edx_rbac.models import UserRole, UserRoleAssignment
from jsonfield.encoder import JSONEncoder
from jsonfield.fields import JSONField
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords

from enterprise_catalog.apps.api.v1.utils import (
    get_enterprise_utm_context,
    update_query_parameters,
)
from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.constants import (
    ACCESS_TO_ALL_ENTERPRISES_TOKEN,
    CONTENT_TYPE_CHOICES,
    json_serialized_course_modes,
)
from enterprise_catalog.apps.catalog.utils import (
    get_content_filter_hash,
    get_content_key,
    get_content_type,
    get_parent_content_key,
    get_sorted_string_from_json,
)


LOGGER = getLogger(__name__)


class CatalogQuery(models.Model):
    """
    Stores a re-usable catalog query.

    .. no_pii:
    """

    content_filter = JSONField(
        blank=False,
        null=False,
        default=dict,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        dump_kwargs={'indent': 4, 'cls': JSONEncoder, 'separators': (',', ':')},
        help_text=_(
            "Query parameters which will be used to filter the discovery service's search/all "
            "endpoint results, specified as a JSON object."
        )
    )
    content_filter_hash = models.CharField(
        null=True,
        unique=True,
        max_length=32,
        editable=False,
    )

    class Meta:
        verbose_name = _("Catalog Query")
        verbose_name_plural = _("Catalog Queries")
        app_label = 'catalog'

    def save(self, *args, **kwargs):  # pylint: disable=arguments-differ
        self.content_filter_hash = get_content_filter_hash(self.content_filter)
        super(CatalogQuery, self).save(*args, **kwargs)

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return "<CatalogQuery with content filter hash '{content_filter_hash}'>".format(
            content_filter_hash=self.content_filter_hash
        )


class EnterpriseCatalog(TimeStampedModel):
    """
    Associates a stored catalog query with an enterprise customer.

    .. no_pii:
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
    )
    title = models.CharField(
        max_length=255,
        blank=False,
        null=False,
    )
    enterprise_uuid = models.UUIDField(
        blank=False,
        null=False,
        db_index=True,
    )
    enterprise_name = models.CharField(
        max_length=255,
        blank=True,
    )
    catalog_query = models.ForeignKey(
        CatalogQuery,
        blank=False,
        null=True,
        related_name='enterprise_catalogs',
        on_delete=models.deletion.SET_NULL,
    )
    enabled_course_modes = JSONField(
        default=json_serialized_course_modes,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        dump_kwargs={'indent': 4, 'cls': JSONEncoder, 'separators': (',', ':')},
        help_text=_('Ordered list of enrollment modes which can be displayed to learners for course runs in'
                    ' this catalog.'),
    )
    publish_audit_enrollment_urls = models.BooleanField(
        default=False,
        help_text=_(
            "Specifies whether courses should be published with direct-to-audit enrollment URLs."
        ),
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Enterprise Catalog")
        verbose_name_plural = _("Enterprise Catalogs")
        app_label = 'catalog'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return (
            "<EnterpriseCatalog with UUID '{uuid}' "
            "for EnterpriseCustomer '{enterprise_uuid}'>".format(
                uuid=self.uuid,
                enterprise_uuid=self.enterprise_uuid
            )
        )

    @property
    def content_metadata(self):
        """
        Helper to retrieve the content metadata associated with the catalog.

        Returns:
            Queryset: The queryset of associated content metadata
        """
        if not self.catalog_query:
            return ContentMetadata.objects.none()
        return self.catalog_query.contentmetadata_set.all()

    def contains_content_keys(self, content_keys):
        """
        Return True if catalog contains the courses/course runs/programs specified by the given content keys, else False

        Note that content is also part of the catalog if its parent is part of the catalog. Assumes that we have a
        ContentMetadata entry for every content id for proper parent/child lookup, but does not error if that is false.
        """
        if not self.catalog_query:
            return False

        content_keys = set(content_keys)
        associated_metadata_content_keys = {metadata_chunk.content_key for metadata_chunk in self.content_metadata}
        contained_in_catalog = True
        for content_key in content_keys:
            try:
                parent_content_key = ContentMetadata.objects.get(content_key=content_key).parent_content_key
            except ContentMetadata.DoesNotExist:
                parent_content_key = None

            # The content key is contained in the catalog if its key is explictly part of the associated metadata, or
            # its parent's key is.
            contained_in_catalog = contained_in_catalog and (
                # pylint: disable=line-too-long
                content_key in associated_metadata_content_keys or parent_content_key in associated_metadata_content_keys
            )
            # Break early as soon as we find a key that is not contained in the catalog
            if not contained_in_catalog:
                return False

        return contained_in_catalog

    def get_content_enrollment_url(self, content_resource, content_key):
        """
        Return enterprise content enrollment page url with the catalog information for the given content key.

        Arguments:
            content_resource (str): The content resource to use in the URL (i.e., "course", "program")
            content_key (str): The content key for the course to be displayed.

        Returns:
            (str): Enterprise landing page url.
        """
        if not content_key or not content_resource:
            return None

        url = '{}/enterprise/{}/{}/{}/enroll/'.format(
            settings.LMS_BASE_URL,
            self.enterprise_uuid,
            content_resource,
            content_key,
        )
        params = get_enterprise_utm_context(self.enterprise_name)
        params['catalog'] = self.uuid

        if self.publish_audit_enrollment_urls:
            params['audit'] = 'true'

        return update_query_parameters(url, params)


class ContentMetadata(TimeStampedModel):
    """
    Stores the JSON metadata for a piece of content, such as a course, course run, or program.
    The metadata is retrieved from the Discovery service /search/all endpoint.

    .. no_pii:
    """

    content_key = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        unique=True,
        help_text=_(
            "The key that represents a piece of content, such as a course, course run, or program."
        )
    )
    content_type = models.CharField(
        max_length=255,
        choices=CONTENT_TYPE_CHOICES,
        blank=False,
        null=False,
    )
    parent_content_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text=_(
            "The key that represents this content's parent, such as a course or program."
        )
    )
    json_metadata = JSONField(
        default={},
        blank=True,
        null=True,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        dump_kwargs={'indent': 4, 'cls': JSONEncoder, 'separators': (',', ':')},
        help_text=_(
            "The metadata about a particular piece content as retrieved from the discovery service's search/all "
            "endpoint results, specified as a JSON object."
        )
    )
    catalog_queries = models.ManyToManyField(CatalogQuery)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Content Metadata")
        verbose_name_plural = _("Content Metadata")
        app_label = 'catalog'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return (
            "<ContentMetadata for '{content_key}'>".format(
                content_key=self.content_key
            )
        )


def associate_content_metadata_with_query(metadata, catalog_query):
    """
    Creates or (possibly) updates a ContentMetadata object for each entry in `metadata`,
    and then associates that object with the `catalog_query` provided.
    Only updates an existing ContentMetadata object if its `json_metadata` field
    differs from the data provided in `metadata`.

    metadata: List of content metadata dictionaries.
    catalog_query: CatalogQuery object

    Returns:
        list: The list of content_keys for the metadata associated with the query.
    """
    metadata_list = []
    for entry in metadata:
        content_key = get_content_key(entry)
        defaults = {
            'content_key': content_key,
            'json_metadata': entry,
            'parent_content_key': get_parent_content_key(entry),
            'content_type': get_content_type(entry),
        }

        try:
            existing_metadata = ContentMetadata.objects.get(content_key=content_key)
        except ContentMetadata.DoesNotExist:
            existing_metadata = None

        if existing_metadata:
            if get_sorted_string_from_json(entry) == get_sorted_string_from_json(existing_metadata.json_metadata):
                # Only update the existing ContentMetadata object if its json has changed,
                # but still associate it with the query
                metadata_list.append(existing_metadata)
                continue

            for key, value in defaults.items():
                setattr(existing_metadata, key, value)
            existing_metadata.save()
        else:
            existing_metadata = ContentMetadata.objects.create(**defaults)

        metadata_list.append(existing_metadata)

    # Setting `clear=True` will remove all prior relationships between
    # the CatalogQuery's associated ContentMetadata objects
    # before setting all new relationships from `metadata_list`.
    # https://docs.djangoproject.com/en/2.2/ref/models/relations/#django.db.models.fields.related.RelatedManager.set
    catalog_query.contentmetadata_set.set(metadata_list, clear=True)
    associated_content_keys = [metadata.content_key for metadata in metadata_list]
    return associated_content_keys


class EnterpriseCatalogFeatureRole(UserRole):
    """
    User role definitions specific to Enterprise Catalog.
     .. no_pii:
    """

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return "EnterpriseCatalogFeatureRole(name={name})".format(name=self.name)

    def __repr__(self):
        """
        Return uniquely identifying string representation.
        """
        return self.__str__()


class EnterpriseCatalogRoleAssignment(UserRoleAssignment):
    """
    Model to map users to an EnterpriseCatalogFeatureRole.
     .. no_pii:
    """

    role_class = EnterpriseCatalogFeatureRole
    enterprise_id = models.UUIDField(blank=True, null=True, verbose_name='Enterprise Customer UUID')

    def get_context(self):
        """
        Return the enterprise customer id or `*` if the user has access to all resources.
        """
        if self.enterprise_id:
            # converting the UUID('ee5e6b3a-069a-4947-bb8d-d2dbc323396c') to 'ee5e6b3a-069a-4947-bb8d-d2dbc323396c'
            return str(self.enterprise_id)
        return ACCESS_TO_ALL_ENTERPRISES_TOKEN

    @classmethod
    def user_assignments_for_role_name(cls, user, role_name):
        """
        Returns assignments for a given user and role name.
        """
        return cls.objects.filter(user__id=user.id, role__name=role_name)

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return "EnterpriseCatalogRoleAssignment(name={name}, user={user})".format(
            name=self.role.name,  # pylint: disable=no-member
            user=self.user.id,
        )

    def __repr__(self):
        """
        Return uniquely identifying string representation.
        """
        return self.__str__()


def update_contentmetadata_from_discovery(catalog_query_id):
    """
    catalog_query_id is a identifer for CatalogQuery objects (int)

    Takes a uuid, looks up catalogquery, uses discovery service client to
    grab fresh metadata, and then create/updates ContentMetadata objects.

    Omits expired course runs from the updated metadata to match old
    edx-enterprise implementatiion.
    """
    client = DiscoveryApiClient()

    try:
        catalog_query = CatalogQuery.objects.get(id=catalog_query_id)
    except CatalogQuery.DoesNotExist:
        catalog_query = None

    if catalog_query:
        query_params = {
            # Omit non-active course runs from the course-discovery results
            'exclude_expired_course_run': True,
            # Increasing page_size will help alleviate the non-deterministic behavior
            # of the /search/all/ endpoint where a content item may appear on multiple
            # pages (e.g., a course is included on both pages 1 and 2). This issue with the
            # /search/all/ endpoint is likely the reason we get duplicate results.
            'page_size': 200,
        }
        metadata = client.get_metadata_by_query(catalog_query.content_filter, query_params=query_params)
        metadata_content_keys = [get_content_key(entry) for entry in metadata]

        LOGGER.info(
            'Retrieved %d content items (%d unique) from course-discovery for catalog query %s: %s',
            len(metadata_content_keys),
            len(set(metadata_content_keys)),
            catalog_query,
            metadata_content_keys
        )

        associated_content_keys = associate_content_metadata_with_query(metadata, catalog_query)
        LOGGER.info(
            'Associated %d content items (%d unique) with catalog query %s: %s',
            len(associated_content_keys),
            len(set(associated_content_keys)),
            catalog_query,
            associated_content_keys,
        )
    else:
        LOGGER.warning(
            'Could not find a CatalogQuery with id %s',
            catalog_query_id,
        )
