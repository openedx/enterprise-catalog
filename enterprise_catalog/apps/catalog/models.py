import collections
from uuid import uuid4

from jsonfield.fields import JSONField
from model_utils.models import TimeStampedModel
from simple_history.models import HistoricalRecords

from django.db import models
from django.utils.translation import gettext as _


class CatalogQuery(models.Model):
    """
    Stores a re-usable catalog query.

    .. no_pii:
    """

    title = models.CharField(
        default='All Content',
        max_length=255,
        blank=False,
        null=False
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

    class Meta(object):
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
    enterprise_uuid = models.UUIDField()
    catalog_query = models.ForeignKey(
        CatalogQuery,
        blank=False,
        null=False,
        related_name='enterprise_catalogs',
        on_delete=models.deletion.CASCADE
    )

    history = HistoricalRecords()

    class Meta(object):
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
    content_key = models.CharField(
        max_length=255,
        blank=False,
        help_text=_(
            "The key that represents a piece of content, such as a course, course run, or program."
        )
    )

    history = HistoricalRecords()

    class Meta(object):
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
