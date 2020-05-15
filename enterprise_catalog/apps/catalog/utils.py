# -*- coding: utf-8 -*-
"""
Utility functions for catalog app.
"""
import hashlib
import json
from logging import getLogger

from edx_rbac.utils import feature_roles_from_jwt
from edx_rest_framework_extensions.auth.jwt.authentication import (
    get_decoded_jwt_from_auth,
)
from edx_rest_framework_extensions.auth.jwt.cookies import \
    get_decoded_jwt as get_decoded_jwt_from_cookie

from enterprise_catalog.apps.catalog.constants import COURSE_RUN


LOGGER = getLogger(__name__)


def get_content_filter_hash(content_filter):
    content_filter_sorted_keys = json.dumps(content_filter, sort_keys=True).encode()
    content_filter_hash = hashlib.md5(content_filter_sorted_keys).hexdigest()
    return content_filter_hash


def get_metadata_hash(metadata):
    """
    This is a temporary duplicate of get_content_filter_hash for logging

    This will likely be removed soon, but could also be updated to hash more of a content metadata
    object as opposed to simply json_metadata
    """
    metadata_sorted_keys = json.dumps(metadata, sort_keys=True).encode()
    metadata_hash = hashlib.md5(metadata_sorted_keys).hexdigest()
    return metadata_hash


def get_content_key(metadata, catalog_uuid=None):
    """
    Returns the content key of a piece of metadata

    Try to get the course/course run key as the content key, falling back to uuid for programs
    """
    content_key = metadata.get('key') or metadata.get('uuid')
    if not content_key:
        LOGGER.info(
            'Unable to retrieve a content key for metadata: %s, from catalog: %s',
            metadata,
            catalog_uuid,
        )

    return content_key


def _partition_aggregation_key(aggregation_key):
    """
    Partitions the aggregation_key field from discovery to return the type and key of the content it represents

    Note that the content_key for a course run refers to a course rather than itself
    """
    content_type, _, content_key = aggregation_key.partition(':')
    return content_type, content_key


def get_parent_content_key(metadata):
    """
    Returns the content key of the parent object from a piece of metadata

    This is meant to be used on metadata from the /search/all discovery endpoint. If the metadata represents a
    course run, then the parent content key is the key of the course it belongs to. Otherwise, returns None
    """
    aggregation_key = metadata.get('aggregation_key', '')
    content_type, content_key = _partition_aggregation_key(aggregation_key)
    parent_content_key = None
    if content_type == COURSE_RUN:
        parent_content_key = content_key

    return parent_content_key


def get_content_type(metadata):
    """
    Returns the content type associated with a piece of metadata
    """
    aggregation_key = metadata.get('aggregation_key', '')
    content_type, _ = _partition_aggregation_key(aggregation_key)
    return content_type


def get_jwt_roles(request):
    """
    Decodes the request's JWT from either cookies or auth payload and returns mapping of features roles from it.
    """
    decoded_jwt = get_decoded_jwt_from_cookie(request) or get_decoded_jwt_from_auth(request)
    if not decoded_jwt:
        return {}
    return feature_roles_from_jwt(decoded_jwt)
