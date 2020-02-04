"""
Rules needed to restrict access to the enterprise catalog service.
"""
import crum
import rules
from edx_rbac.utils import request_user_has_implicit_access_via_jwt
from edx_rest_framework_extensions.auth.jwt.authentication import (
    get_decoded_jwt_from_auth,
)
from edx_rest_framework_extensions.auth.jwt.cookies import get_decoded_jwt

from enterprise_catalog.apps.catalog.constants import (
    ENTERPRISE_CATALOG_ADMIN_ROLE,
)


@rules.predicate
def has_implicit_access_to_catalog(user, obj):  # pylint: disable=unused-argument
    """
    Check that if request user has implicit access to `ENTERPRISE_CATALOG_ADMIN_ROLE` role.

    Returns:
        boolean: whether the request user has access or not
    """
    request = crum.get_current_request()
    decoded_jwt = get_decoded_jwt(request) or get_decoded_jwt_from_auth(request)
    return request_user_has_implicit_access_via_jwt(decoded_jwt, ENTERPRISE_CATALOG_ADMIN_ROLE, obj)


rules.add_perm('catalog.has_admin_access', has_implicit_access_to_catalog)
