# -*- coding: utf-8 -*-
"""Broadly-useful mixins for use in automated tests."""
from __future__ import absolute_import

import jwt
from django.conf import settings
from django.test.client import RequestFactory
from edx_rest_framework_extensions.auth.jwt.cookies import jwt_cookie_name
from edx_rest_framework_extensions.auth.jwt.tests.utils import (
    generate_jwt_token,
    generate_unversioned_payload,
)
from rest_framework.test import APITestCase

from enterprise_catalog.apps.catalog.constants import (
    ENTERPRISE_CATALOG_ADMIN_ROLE,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    USER_PASSWORD,
    UserFactory,
)


class JwtMixin():
    """ Mixin with JWT-related helper functions. """
    JWT_SECRET_KEY = settings.JWT_AUTH['JWT_SECRET_KEY']
    issuer = settings.JWT_AUTH['JWT_ISSUERS'][0]['ISSUER']

    def generate_token(self, payload, secret=None):
        """Generate a JWT token with the provided payload."""
        secret = secret or self.JWT_SECRET_KEY
        token = jwt.encode(dict(payload, iss=self.issuer), secret).decode('utf-8')
        return token

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
        self.user = UserFactory(is_staff=True)
        self.client.login(username=self.user.username, password=USER_PASSWORD)
        self.set_jwt_cookie(ENTERPRISE_CATALOG_ADMIN_ROLE)

    def set_up_non_staff(self):
        """
        Helper for logging in as a non-staff user
        """
        self.client.logout()
        non_staff_user = UserFactory()
        self.client.login(username=non_staff_user.username, password=USER_PASSWORD)

    def set_up_non_catalog_admin(self):
        """
        Helpr for logging in as a user that does not have the appropriate role(s) in the JWT
        """
        self.client.logout()
        non_staff_user = UserFactory()
        self.client.login(username=non_staff_user.username, password=USER_PASSWORD)
        self.set_jwt_cookie('invalid_role')

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
