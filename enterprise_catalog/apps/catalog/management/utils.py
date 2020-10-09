""" Utility functions for catalog management """
from enterprise_catalog.apps.catalog.models import ContentMetadata


def get_all_content_keys():
    """
    Returns a list of content keys for all ContentMetadata objects.
    """
    all_content_metadata = ContentMetadata.objects.values_list('content_key', flat=True)
    return list(all_content_metadata)
