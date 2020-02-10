import collections
from logging import getLogger
from uuid import uuid4

from django.db import models
from django.utils.translation import gettext as _
from jsonfield.fields import JSONField
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords

from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.catalog.constants import (
    CONTENT_TYPE_CHOICES,
    json_serialized_course_modes,
)
from enterprise_catalog.apps.catalog.utils import (
    get_content_filter_hash,
    get_content_key,
    get_content_type,
    get_parent_content_key,
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
        null=False
    )
    enterprise_uuid = models.UUIDField(
        blank=False,
        null=False,
        db_index=True,
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
        unique_together = (("enterprise_uuid", "catalog_query"),)
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

    def contains_content_keys(self, content_keys):
        """
        Return True if catalog contains the courses/course runs/programs specified by the given content keys, else False

        Note that content is also part of the catalog if its parent is part of the catalog. Assumes that we have a
        ContentMetadata entry for every content id for proper parent/child lookup, but does not error if that is false.
        """
        if not self.catalog_query:
            return False

        content_keys = set(content_keys)
        associated_metadata_content_keys = {metadata_chunk.content_key for metadata_chunk
                                            in self.catalog_query.contentmetadata_set.all()}
        contained_in_catalog = True
        for content_key in content_keys:
            try:
                parent_content_key = ContentMetadata.objects.get(content_key=content_key).parent_content_key
            except ContentMetadata.DoesNotExist:
                parent_content_key = None

            # The content key is contained in the catalog if its key is explictly part of the associated metadata, or
            # its parent's key is.
            contained_in_catalog = contained_in_catalog and (content_key in associated_metadata_content_keys
                or parent_content_key in associated_metadata_content_keys)
            # Break early as soon as we find a key that is not contained in the catalog
            if not contained_in_catalog:
                return False

        return contained_in_catalog


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
    get_or_create a content metadata object for entry in metadata
    and then associate that object with the catalog_query provided.

    metadata: Dictionary containing metadata
    catalog_query: CatalogQuery object

    Returns set of content_keys
    """
    content_keys = set()
    for entry in metadata.get('results', []):
        content_key = get_content_key(entry)
        defaults = {
            'content_key': content_key,
            'parent_content_key': get_parent_content_key(entry),
            'content_type': get_content_type(entry),
        }
        cm, __ = ContentMetadata.objects.update_or_create(
            json_metadata=entry,
            defaults=defaults,
        )
        LOGGER.info(
            'Associating content_metadata %s with catalog_query %s.',
            cm,
            catalog_query
        )
        catalog_query.contentmetadata_set.add(cm)
        content_keys.add(content_key)
    return content_keys


def unassociate_content_metadata_from_catalog_query(content_keys, catalog_query):
    """
    content_keys: Set of content keys
    catalog_query: CatalogQuery object

    Remove association of content_metadata objects from catalog_query if
    the content_metadata object does not have a content_key included in the
    content_keys set provided.
    """

    for cm in catalog_query.contentmetadata_set.all():
        if cm.content_key not in content_keys:
            LOGGER.info(
                'Removing association for content_metadata %s with catalog_query %s.',
                cm,
                catalog_query
            )
            catalog_query.contentmetadata_set.remove(cm)


def update_contentmetadata_from_discovery(catalog_uuid):
    """
    catalog_uuid is a uuid (str)

    Takes a uuid, looks up catalogquery, uses discovery service client to
    grab fresh metadata, and then create/updates ContentMetadata objects.
    """
    client = DiscoveryApiClient()

    catalog = EnterpriseCatalog.objects.get(uuid=catalog_uuid)
    catalog_query = catalog.catalog_query
    metadata = client.get_metadata_by_query(catalog_query.content_filter)

    content_keys = associate_content_metadata_with_query(metadata, catalog_query)

    unassociate_content_metadata_from_catalog_query(content_keys, catalog_query)
