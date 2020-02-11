from django.shortcuts import get_object_or_404
from six.moves.urllib.parse import quote_plus, unquote

from enterprise_catalog.apps.catalog.models import (
    EnterpriseCatalog,
)


def unquote_course_keys(course_keys):
    """
    Maintain plus characters in course/course run keys from query parameters
    """
    return [unquote(quote_plus(course_key)) for course_key in course_keys]

def get_enterprise_uuid_by_catalog_uuid(request, uuid, *args, **kwargs):
    catalog = get_object_or_404(EnterpriseCatalog, uuid=uuid)
    return str(catalog.enterprise_uuid)

def get_enterprise_uuid_from_request_data(request, *args, **kwargs):
    return request.data.get('enterprise_customer')
