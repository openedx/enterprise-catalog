import collections

from jsonfield.fields import JSONField

from django.db import models

class ContentCatalog(TimeStampedModel):
    """
    Stores a re-usable content catalog query.

    This stored catalog query used in `EnterpriseContentCatalog` objects to build catalog's query field.
    This is a saved instance of `query` that can be re-used accross different catalogs.

    .. no_pii:
    """
    query = JSONField(
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
  