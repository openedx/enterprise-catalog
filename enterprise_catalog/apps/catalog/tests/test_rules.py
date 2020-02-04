# -*- coding: utf-8 -*-
"""
Tests for the `edx-enterprise` models module.
"""

from __future__ import absolute_import, unicode_literals, with_statement

import ddt
import mock

from enterprise_catalog.apps.api.v1.tests.mixins import APITestMixin
from enterprise_catalog.apps.catalog.constants import (
    ENTERPRISE_ADMIN_ROLE,
    ENTERPRISE_CATALOG_ADMIN_ROLE,
    ENTERPRISE_OPERATOR_ROLE,
)


@ddt.ddt
class TestCatalogRBACPermissions(APITestMixin):
    """
    Test defined django rules for authorization checks.
    """

    @mock.patch('enterprise_catalog.apps.catalog.rules.crum.get_current_request')
    @ddt.data(
        'catalog.has_admin_access',
    )
    def test_has_implicit_access_catalog_admin(self, permission, get_current_request_mock):
        get_current_request_mock.return_value = self.get_request_with_jwt_cookie(ENTERPRISE_CATALOG_ADMIN_ROLE)
        assert self.user.has_perm(permission)

    @mock.patch('enterprise_catalog.apps.catalog.rules.crum.get_current_request')
    @ddt.data(
        'catalog.has_admin_access',
    )
    def test_has_implicit_access_enterprise_admin(self, permission, get_current_request_mock):
        get_current_request_mock.return_value = self.get_request_with_jwt_cookie(ENTERPRISE_ADMIN_ROLE)
        assert self.user.has_perm(permission)

    @mock.patch('enterprise_catalog.apps.catalog.rules.crum.get_current_request')
    @ddt.data(
        'catalog.has_admin_access',
    )
    def test_has_implicit_access_enterprise_operator(self, permission, get_current_request_mock):
        get_current_request_mock.return_value = self.get_request_with_jwt_cookie(ENTERPRISE_OPERATOR_ROLE)
        assert self.user.has_perm(permission)
