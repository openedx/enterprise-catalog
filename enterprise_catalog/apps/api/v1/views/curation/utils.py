from uuid import UUID

from rest_framework.exceptions import ParseError


def get_enterprise_uuid_from_request_query_params(request):
    """
    Extracts enterprise customer UUID from query parameters.
    """
    enterprise_customer_uuid = request.query_params.get('enterprise_customer')
    if not enterprise_customer_uuid:
        return None
    try:
        return UUID(enterprise_customer_uuid)
    except ValueError:
        raise ParseError('{} is not a valid uuid.'.format(enterprise_customer_uuid))


def get_enterprise_uuid_from_request_data(request):
    """
    Extracts enterprise_customer UUID from the request payload.
    """
    enterprise_customer_uuid = request.data.get('enterprise_customer')

    if not enterprise_customer_uuid:
        return None

    try:
        return UUID(enterprise_customer_uuid)
    except ValueError as ex:
        raise ParseError('{} is not a valid uuid.'.format(enterprise_customer_uuid)) from ex


def get_content_keys_from_request_data(request):
    """
    Extracts content keys from the request payload.
    """
    content_keys = request.data.get('content_keys', [])
    return content_keys
