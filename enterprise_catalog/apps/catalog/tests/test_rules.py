# -*- coding: utf-8 -*-
"""
Tests for the edx-rbac rules predicates.
"""
import uuid
import ddt
import mock

from enterprise_catalog.apps.api.v1.tests.mixins import APITestMixin
from enterprise_catalog.apps.catalog.constants import (
    SYSTEM_ENTERPRISE_ADMIN_ROLE,
    SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE,
    SYSTEM_ENTERPRISE_OPERATOR_ROLE,
)


TEST_ENTERPRISE_UUID = 'b13f423b-6f01-40af-af70-5397cbba83ca'
ALL_ACCESS_CONTEXT = '*'


@ddt.ddt
class TestCatalogRBACPermissions(APITestMixin):
    """
    Test defined django rules for authorization checks.
    """

    @mock.patch('enterprise_catalog.apps.catalog.rules.crum.get_current_request')
    @ddt.data(
        ('catalog.has_admin_access', SYSTEM_ENTERPRISE_ADMIN_ROLE, TEST_ENTERPRISE_UUID),
        ('catalog.has_admin_access', SYSTEM_ENTERPRISE_ADMIN_ROLE, ALL_ACCESS_CONTEXT),
    )
    @ddt.unpack
    def test_has_no_implicit_access(self, permission, system_wide_role, context, get_current_request_mock):
        get_current_request_mock.return_value = self.get_request_with_jwt_cookie(system_wide_role, context)
        assert not self.user.has_perm(permission, TEST_ENTERPRISE_UUID)

    @mock.patch('enterprise_catalog.apps.catalog.rules.crum.get_current_request')
    @ddt.data(
        ('catalog.has_admin_access', SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE, TEST_ENTERPRISE_UUID),
        ('catalog.has_admin_access', SYSTEM_ENTERPRISE_OPERATOR_ROLE, TEST_ENTERPRISE_UUID),
        ('catalog.has_admin_access', SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE, ALL_ACCESS_CONTEXT),
        ('catalog.has_admin_access', SYSTEM_ENTERPRISE_OPERATOR_ROLE, ALL_ACCESS_CONTEXT),
    )
    @ddt.unpack
    def test_has_implicit_access(self, permission, system_wide_role, context, get_current_request_mock):
        get_current_request_mock.return_value = self.get_request_with_jwt_cookie(system_wide_role, context)
        assert self.user.has_perm(permission, TEST_ENTERPRISE_UUID)

    @mock.patch('enterprise_catalog.apps.catalog.rules.crum.get_current_request')
    @ddt.data(
        ('catalog.has_admin_access', SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE),
        ('catalog.has_admin_access', SYSTEM_ENTERPRISE_OPERATOR_ROLE),
    )
    @ddt.unpack
    def test_has_implicit_access_no_context(self, permission, system_wide_role, get_current_request_mock):
        get_current_request_mock.return_value = self.get_request_with_jwt_cookie(system_wide_role)
        assert not self.user.has_perm(permission, TEST_ENTERPRISE_UUID)

    @mock.patch('enterprise_catalog.apps.catalog.rules.crum.get_current_request')
    @ddt.data(
        ('catalog.has_admin_access', SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE),
        ('catalog.has_admin_access', SYSTEM_ENTERPRISE_OPERATOR_ROLE),
    )
    @ddt.unpack
    def test_has_implicit_access_incorrent_context(self, permission, system_wide_role, get_current_request_mock):
        get_current_request_mock.return_value = self.get_request_with_jwt_cookie(system_wide_role, uuid.uuid4())
        assert not self.user.has_perm(permission, TEST_ENTERPRISE_UUID)

    @mock.patch('enterprise_catalog.apps.catalog.rules.crum.get_current_request')
    @ddt.data('catalog.has_admin_access')
    def test_has_explicit_access(self, permission, get_current_request_mock):
        get_current_request_mock.return_value = self.get_request_with_jwt_cookie()
        assert self.user.has_perm(permission, str(self.enterprise_uuid))
