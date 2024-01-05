from enterprise_catalog.apps.catalog.filters import does_query_match_content
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
    EnterpriseCatalog,
)


def get_catalogs_for_content(course_key, catalog_filter=None):
    """
    Retrieve all catalogs that contain the given course_key.

    Arguments:
        course_key (str): Course key to lookup the content metadata object for comparison against the catalog query
            filters

        catalog_filter (dict): Optional filter to apply to the catalogs queryset
    """
    content_object = ContentMetadata.objects.get(content_key=course_key)
    if catalog_filter is None:
        catalog_filter = {}
    included_catalogs = []
    for catalog in EnterpriseCatalog.objects.filter(**catalog_filter):
        if does_query_match_content(catalog.catalog_query.content_filter, content_object.json_metadata):
            included_catalogs.append(catalog)

    return included_catalogs
