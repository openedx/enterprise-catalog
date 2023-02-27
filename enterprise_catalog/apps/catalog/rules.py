"""
Rules needed to restrict access to the enterprise catalog service.
"""
import crum
import rules
from edx_rbac.utils import (
    request_user_has_implicit_access_via_jwt,
    user_has_access_via_database,
)
from edx_rest_framework_extensions.auth.jwt.authentication import (
    get_decoded_jwt_from_auth,
)
from edx_rest_framework_extensions.auth.jwt.cookies import get_decoded_jwt

from enterprise_catalog.apps.catalog.constants import (
    ACCESS_TO_ALL_ENTERPRISES_TOKEN,
    ENTERPRISE_CATALOG_ADMIN_ROLE,
    ENTERPRISE_CATALOG_LEARNER_ROLE,
    PERMISSION_HAS_ADMIN_ACCESS,
    PERMISSION_HAS_LEARNER_ACCESS,
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
    PERMISSION_HAS_ADMIN_ACCESS,
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
    PERMISSION_HAS_LEARNER_ACCESS,
    (has_implicit_access_to_catalog_learner | has_explicit_access_to_catalog_learner
     | has_implicit_access_to_catalog_admin | has_explicit_access_to_catalog_admin)
)


def has_access_to_all_enterprises(enterprise_ids):
    """
    Returns true if the given set of enterprise customer ids contains the "wildcard" access identifier.
    """
    return ACCESS_TO_ALL_ENTERPRISES_TOKEN in enterprise_ids


def enterprises_with_admin_access(request):
    """
    Returns a set of enterprise ids to which a user has been granted admin access.

    Note that this may include the "*" wildcard identifier, which means that the user
    is allowed access to all enterprises.
    """
    if hasattr(request, 'user') and request.user.is_superuser:
        return {ACCESS_TO_ALL_ENTERPRISES_TOKEN}
    eligible_enterprises_jwt_admin_access = _enterprises_with_jwt_admin_access(request)
    if hasattr(request, 'user'):
        eligible_enterprises_jwt_admin_access += _enterprises_with_database_admin_access(request.user)
    return set(eligible_enterprises_jwt_admin_access)


def _enterprises_with_database_admin_access(user):
    """
    Returns a list of enterprise ids to which a user has been granted admin access via database assignment.
    """
    return [
        assignment.get_context() for assignment in
        EnterpriseCatalogRoleAssignment.user_assignments_for_role_name(
            user,
            ENTERPRISE_CATALOG_ADMIN_ROLE
        )
    ]


def _enterprises_with_jwt_admin_access(request):
    """
    Returns a list of enterprise ids to which a user has been granted admin access via JWT roles.
    """
    roles_from_jwt = get_jwt_roles(request)
    return roles_from_jwt.get(ENTERPRISE_CATALOG_ADMIN_ROLE, [])
