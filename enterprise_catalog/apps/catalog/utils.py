# -*- coding: utf-8 -*-
"""
Utility functions for catalog app.
"""
from __future__ import absolute_import, division, unicode_literals

import hashlib
import json

from enterprise_catalog.apps.catalog.constants import COURSE_RUN


def get_content_filter_hash(content_filter):
    content_filter_sorted_keys = json.dumps(content_filter, sort_keys=True).encode()
    content_filter_hash = hashlib.md5(content_filter_sorted_keys).hexdigest()
    return content_filter_hash

def get_content_key(metadata):
    """
    Returns the content key of a piece of metadata

    Try to get the course/course run key as the content key, falling back to uuid for programs
    """
    return metadata.get('key') or metadata.get('uuid')

def _partition_aggregation_key(aggregation_key):
    """
    Partitions the aggregation_key field from discovery to return the type and key of the content it represents
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
