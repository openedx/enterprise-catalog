"""
Rules needed to restrict access to the enterprise catalog service.
"""
import crum
import rules
from edx_rest_framework_extensions.auth.jwt.authentication import (
    get_decoded_jwt_from_auth,
)
from edx_rest_framework_extensions.auth.jwt.cookies import get_decoded_jwt

from edx_rbac.utils import (
    request_user_has_implicit_access_via_jwt,
    user_has_access_via_database,
)
from enterprise_catalog.apps.catalog.constants import (
    ACCESS_TO_ALL_ENTERPRISES_TOKEN,
    ENTERPRISE_CATALOG_ADMIN_ROLE,
    ENTERPRISE_CATALOG_LEARNER_ROLE,
)
from enterprise_catalog.apps.catalog.models import (
    EnterpriseCatalogRoleAssignment,
)
from enterprise_catalog.apps.catalog.utils import get_jwt_roles


@rules.predicate
def has_implicit_access_to_catalog_admin(user, context):  # pylint: disable=unused-argument
    """
    Check that if request user has implicit access to `ENTERPRISE_CATALOG_ADMIN_ROLE` role.

    Returns:
        boolean: whether the request user has access or not
    """
    if not context:
        return False
    request = crum.get_current_request()
    decoded_jwt = get_decoded_jwt(request) or get_decoded_jwt_from_auth(request)
    return request_user_has_implicit_access_via_jwt(decoded_jwt, ENTERPRISE_CATALOG_ADMIN_ROLE, context)


@rules.predicate
def has_explicit_access_to_catalog_admin(user, context):
    """
    Check that if request user has explicit access to `ENTERPRISE_CATALOG_ADMIN_ROLE` feature role.
    Returns:
        boolean: whether the request user has access or not
    """
    if not context:
        return False
    return user_has_access_via_database(
        user,
        ENTERPRISE_CATALOG_ADMIN_ROLE,
        EnterpriseCatalogRoleAssignment,
        context,
    )


rules.add_perm(
    'catalog.has_admin_access',
    has_implicit_access_to_catalog_admin | has_explicit_access_to_catalog_admin
)


@rules.predicate
def has_implicit_access_to_catalog_learner(user, context):  # pylint: disable=unused-argument
    """
    Check that if request user has implicit access to `ENTERPRISE_CATALOG_LEARNER_ROLE` role.

    Returns:
        boolean: whether the request user has access or not
    """
    if not context:
        return False
    request = crum.get_current_request()
    decoded_jwt = get_decoded_jwt(request) or get_decoded_jwt_from_auth(request)
    return request_user_has_implicit_access_via_jwt(decoded_jwt, ENTERPRISE_CATALOG_LEARNER_ROLE, context)


@rules.predicate
def has_explicit_access_to_catalog_learner(user, context):
    """
    Check that if request user has explicit access to `ENTERPRISE_CATALOG_LEARNER_ROLE` feature role.
    Returns:
        boolean: whether the request user has access or not
    """
    if not context:
        return False
    return user_has_access_via_database(
        user,
        ENTERPRISE_CATALOG_LEARNER_ROLE,
        EnterpriseCatalogRoleAssignment,
        context,
    )


rules.add_perm(
    'catalog.has_learner_access',
    (has_implicit_access_to_catalog_learner | has_explicit_access_to_catalog_learner
     | has_implicit_access_to_catalog_admin | has_explicit_access_to_catalog_admin)
)
