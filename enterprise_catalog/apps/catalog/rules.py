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


def has_access_to_all_enterprises(enterprise_ids):
    """
    Returns true if the given set of enterprise customer ids contains the "wildcard" access identifier.
    """
    return ACCESS_TO_ALL_ENTERPRISES_TOKEN in enterprise_ids


def enterprises_with_admin_access(user):
    """
    Returns a set of enterprise ids to which a user has been granted admin access.

    Note that this may include the "*" wildcard identifier, which means that the user
    is allowed access to all enterprises.
    """
    if user.is_superuser:
        return {ACCESS_TO_ALL_ENTERPRISES_TOKEN}
    return set(_enterprises_with_jwt_admin_access() + _enterprises_with_database_admin_access(user))


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


def _enterprises_with_jwt_admin_access():
    """
    Returns a list of enterprise ids to which a user has been granted admin access via JWT roles.
    """
    request = crum.get_current_request()
    roles_from_jwt = get_jwt_roles(request)
    return roles_from_jwt.get(ENTERPRISE_CATALOG_ADMIN_ROLE, [])
