import collections
from uuid import uuid4

from django.db import models
from django.utils.translation import gettext as _
from jsonfield.fields import JSONField
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords

from enterprise_catalog.apps.catalog.constants import (
    CONTENT_TYPE_CHOICES,
    json_serialized_course_modes,
)


class CatalogQuery(models.Model):
    """
    Stores a re-usable catalog query.

    .. no_pii:
    """

    title = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        unique=True,
    )
    content_filter = JSONField(
        default={},
        blank=True,
        null=True,
        load_kwargs={'object_pairs_hook': collections.OrderedDict},
        help_text=_(
            "Query parameters which will be used to filter the discovery service's search/all endpoint results, "
            "specified as a JSON object. An empty JSON object means that all available content items will be "
            "included in the catalog."
        )
    )

    class Meta:
        verbose_name = _("Catalog Query")
        verbose_name_plural = _("Catalog Queries")
        app_label = 'catalog'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return "<CatalogQuery '{title}'>".format(title=self.title)


class EnterpriseCatalog(TimeStampedModel):
    """
    Associates a stored catalog query with an enterprise customer.

    .. no_pii:
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False
    )
    title = models.CharField(
        max_length=255,
        blank=False,
        null=False
    )
    enterprise_uuid = models.UUIDField(
        blank=False,
        null=False,
    )
    catalog_query = models.ForeignKey(
        CatalogQuery,
        blank=False,
        null=False,
        related_name='enterprise_catalogs',
        on_delete=models.deletion.CASCADE
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
        )
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


class CatalogContentKey(TimeStampedModel):
    """
    Associates a stored catalog query with an enterprise customer.

    .. no_pii:
    """

    catalog_query = models.ForeignKey(
        CatalogQuery,
        blank=False,
        null=False,
        related_name='catalog_content_keys',
        on_delete=models.deletion.CASCADE
    )
    content_key = models.ForeignKey(
        ContentMetadata,
        to_field='content_key',
        db_column='content_key',
        blank=False,
        null=False,
        related_name='catalog_content_keys',
        on_delete=models.deletion.CASCADE
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Catalog Content Key")
        verbose_name_plural = _("Catalog Content Keys")
        unique_together = (("catalog_query", "content_key"),)
        app_label = 'catalog'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return (
            "<CatalogContentKey for CatalogQuery '{catalog_query_id}' "
            "and content_key '{content_key}'>".format(
                catalog_query_id=self.catalog_query.id,
                content_key=self.content_key
            )
        )
