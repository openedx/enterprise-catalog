"""
Utility functions for catalog app.
"""
import hashlib
import json
import tracemalloc
from logging import getLogger

from edx_rbac.utils import feature_roles_from_jwt
from edx_rest_framework_extensions.auth.jwt.authentication import (
    get_decoded_jwt_from_auth,
)
from edx_rest_framework_extensions.auth.jwt.cookies import \
    get_decoded_jwt as get_decoded_jwt_from_cookie

from enterprise_catalog.apps.catalog.constants import COURSE_RUN, DEFAULT_NUM_ALLOCATIONS_TO_PRINT


LOGGER = getLogger(__name__)


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


def get_sorted_string_from_json(json_metadata):
    """
    Get the string representing a json piece of metadata in alphabetical order for comparisons.

    Arguments:
        json_metadata (json): The json metadata of a particular piece of content metadata.

    Returns:
        string: The json metadata as a sorted string
    """
    return sorted(json.dumps(json_metadata))


def batch(iterable, batch_size=1):
    """
    Break up an iterable into equal-sized batches.

    Arguments:
        iterable (e.g. list): an iterable to batch
        batch_size (int): the size of each batch. Defaults to 1.
    Returns:
        generator: iterates through each batch of an iterable
    """
    iterable_len = len(iterable)
    for index in range(0, iterable_len, batch_size):
        yield iterable[index:min(index + batch_size, iterable_len)]


def print_memory_snapshot(num_allocations=DEFAULT_NUM_ALLOCATIONS_TO_PRINT):
    """
    Logs the n (n=num_allocations) largest memory allocations made by our application.

    Uses tracemalloc to take a snapshot of the Python application's memory usage and
    log details of the n largest allocations including the line of source code
    responsible, size of memory allocated for the given object, the count (number of


    Arguments:
        num_allocations (int): number of allocation details to log
    """
    snapshot = tracemalloc.take_snapshot()
    stats = ''
    for stat in snapshot.statistics('filename')[:num_allocations]:
        stats += str(stat) + '\n'
    LOGGER.info('Printing memory snapshot for top {} allocations:\n{}'.format(num_allocations, stats))
