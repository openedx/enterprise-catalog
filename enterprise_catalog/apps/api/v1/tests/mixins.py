# -*- coding: utf-8 -*-
"""Broadly-useful mixins for use in automated tests."""

import uuid

from django.test.client import RequestFactory
from edx_rest_framework_extensions.auth.jwt.cookies import jwt_cookie_name
from edx_rest_framework_extensions.auth.jwt.tests.utils import (
    generate_jwt_token,
    generate_unversioned_payload,
)
from rest_framework.test import APITestCase

from enterprise_catalog.apps.catalog.constants import (
    ENTERPRISE_CATALOG_ADMIN_ROLE,
    ENTERPRISE_CATALOG_LEARNER_ROLE,
)
from enterprise_catalog.apps.catalog.models import (
    EnterpriseCatalogFeatureRole,
    EnterpriseCatalogRoleAssignment,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    USER_PASSWORD,
    EnterpriseCatalogRoleAssignmentFactory,
    UserFactory,
)


class JwtMixin():
    """ Mixin with JWT-related helper functions. """
    def get_request_with_jwt_cookie(self, system_wide_role=None, context=None):
        """
        Set jwt token in cookies.
        """
        payload = generate_unversioned_payload(self.user)
        if system_wide_role:
            role_data = '{system_wide_role}'.format(system_wide_role=system_wide_role)
            if context is not None:
                role_data += ':{context}'.format(context=context)
            payload.update({
                'roles': [role_data]
            })
        jwt_token = generate_jwt_token(payload)
        request = RequestFactory().get('/')
        request.COOKIES[jwt_cookie_name()] = jwt_token
        return request

    def set_jwt_cookie(self, system_wide_role=None, context=None):
        """
        Set jwt token in cookies
        """
        role_data = '{system_wide_role}'.format(system_wide_role=system_wide_role)
        if context is not None:
            role_data += ':{context}'.format(context=context)

        payload = generate_unversioned_payload(self.user)
        payload.update({
            'roles': [role_data]
        })
        jwt_token = generate_jwt_token(payload)

        self.client.cookies[jwt_cookie_name()] = jwt_token


class APITestMixin(JwtMixin, APITestCase):
    """
    Mixin for functions shared between different API test classes
    """

    def setUp(self):
        super(APITestMixin, self).setUp()
        self.enterprise_uuid = uuid.uuid4()
        self.enterprise_name = 'Test Enterprise'

    def set_up_staff(self):
        """
        Helper for setting up tests as a staff user
        """
        self.user = UserFactory(is_staff=True)
        self.client.login(username=self.user.username, password=USER_PASSWORD)
        self.role = EnterpriseCatalogFeatureRole.objects.get(name=ENTERPRISE_CATALOG_ADMIN_ROLE)
        self.role_assignment = EnterpriseCatalogRoleAssignmentFactory(
            role=self.role,
            user=self.user,
            enterprise_id=self.enterprise_uuid
        )
        self.set_jwt_cookie(ENTERPRISE_CATALOG_ADMIN_ROLE, self.enterprise_uuid)

    def set_up_catalog_learner(self):
        """
        Helper for setting up tests as a catalog learner
        """
        self.user = UserFactory()
        self.client.login(username=self.user.username, password=USER_PASSWORD)
        self.role = EnterpriseCatalogFeatureRole.objects.get(name=ENTERPRISE_CATALOG_LEARNER_ROLE)
        self.role_assignment = EnterpriseCatalogRoleAssignmentFactory(
            role=self.role,
            user=self.user,
            enterprise_id=self.enterprise_uuid
        )
        self.set_jwt_cookie(ENTERPRISE_CATALOG_LEARNER_ROLE, self.enterprise_uuid)

    def set_up_superuser(self):
        """
        Helper for logging in as a superuser
        """
        superuser = UserFactory(is_superuser=True)
        self.client.login(username=superuser.username, password=USER_PASSWORD)

    def set_up_invalid_jwt_role(self):
        """
        Helper for logging in as a user that does not have the appropriate role(s) in the JWT
        """
        self.set_jwt_cookie('invalid_role')

    def remove_role_assignments(self):
        """
        Helper for removing any existing `EnterpriseCatalogRoleAssignment` objects in order
        to test implicit JWT access.
        """
        EnterpriseCatalogRoleAssignment.objects.all().delete()

    def assert_correct_contains_response(self, url, expected_value):
        """
        Helper to assert that the contains_content_items endpoint specified by the url returns the correct value
        """
        response = self.client.get(url)
        self.assertEqual(response.json()['contains_content_items'], expected_value)

    def add_metadata_to_catalog(self, catalog, metadata):
        """
        Adds the given pieces of metadata to a catalog

        Args:
            catalog (EnterpriseCatalog): Enterprise catalog to associate the metadata with
            metadata (iterable of ContentMetadata): Iterable of 1 or more pieces of ContentMetadata to add to a catalog
        """
        catalog.catalog_query.contentmetadata_set.add(*metadata)
