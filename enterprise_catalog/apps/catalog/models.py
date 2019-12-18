import collections

from jsonfield.fields import JSONField

from django.db import models
from django.utils.translation import gettext as _


class ContentCatalogQuery(models.Model):
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
        verbose_name = _("Content Catalog Query")
        verbose_name_plural = _("Content Catalog Queries")
        app_label = 'catalog'

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return "<ContentCatalogQuery '{title}' >".format(title=self.title)
