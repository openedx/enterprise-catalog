"""
Utility functions for catalog app.
"""
import hashlib
import json
from datetime import datetime
from logging import getLogger
from urllib.parse import urljoin

from django.conf import settings
from django.db.models import Q
from edx_rbac.utils import feature_roles_from_jwt
from edx_rest_framework_extensions.auth.jwt.authentication import (
    get_decoded_jwt_from_auth,
)
from edx_rest_framework_extensions.auth.jwt.cookies import \
    get_decoded_jwt as get_decoded_jwt_from_cookie
from pytz import UTC

from enterprise_catalog.apps.catalog.constants import COURSE, COURSE_RUN


LOGGER = getLogger(__name__)


def get_content_filter_hash(content_filter):
    content_filter_sorted_keys = json.dumps(content_filter, sort_keys=True).encode()
    content_filter_hash = hashlib.md5(content_filter_sorted_keys).hexdigest()
    return content_filter_hash


def get_content_uuid(metadata):
    """
    Returns the content uuid for a piece of metadata. Returns None for course runs.
    """
    return metadata.get('uuid')


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


def batch(iterable, batch_size=1):
    """
    Break up an iterable into equal-sized batches.

    Arguments:
        iterable (e.g. list): an iterable to batch
        batch_size (int): the size of each batch. Defaults to 1.
    Returns:
        generator: iterates through each batch of an iterable
    """
    iterable_len = len(iterable) if iterable is not None else 0
    for index in range(0, iterable_len, batch_size):
        yield iterable[index:min(index + batch_size, iterable_len)]


def localized_utcnow():
    """Helper function to return localized utcnow()."""
    return UTC.localize(datetime.utcnow())  # pylint: disable=no-value-for-parameter


def enterprise_proxy_login_url(slug, next_url=None):
    url = urljoin(settings.LMS_BASE_URL, f'/enterprise/proxy-login/?enterprise_slug={slug}')
    if next_url:
        url += f'&next={next_url}'
    return url


def batch_by_pk(ModelClass, extra_filter=Q(), batch_size=10000):
    """
    yield per batch efficiently
    using limit/offset does a lot of table scanning to reach higher offsets
    this scanning can be slow on very large tables
    if you order by pk, you can use the pk as a pivot rather than offset
    this utilizes the index, which is faster than scanning to reach offset
    Example usage:
    course_only_filter = Q(content_type='course')
    for items_batch in batch_by_pk(ContentMetadata, extra_filter=course_only_filter):
        for item in items_batch:
            ...
    """
    qs = ModelClass.objects.filter(extra_filter).order_by('pk')[:batch_size]
    while qs.exists():
        yield qs
        # qs.last() doesn't work here because we've already sliced
        # loop through so we eventually grab the last one
        for item in qs:
            start_pk = item.pk
        qs = ModelClass.objects.filter(pk__gt=start_pk).filter(extra_filter).order_by('pk')[:batch_size]


def to_timestamp(datetime_str):
    """
    Takes a formatted date string to convert it to an unix/epoch timestamp.

    Ex. to_timestamp("2024-07-30T00:00:00Z") -> 1722297600.0

    The decimal represents a timestamp epoch time down to the millisecond.

    This is useful if we need to pass epoch time to an indexable Algolia value
    which requires it to be in epoch format in order for the indexed field to be
    filtered/sorted.
    """
    try:
        dt = datetime.fromisoformat(datetime_str)
        return dt.timestamp()
    except (ValueError, TypeError) as exc:
        LOGGER.error(f"[to_timestamp][{exc}] Could not parse date string: {datetime_str}")
        return None


def get_course_run_by_uuid(course, course_run_uuid):
    """
    Find a course_run based on uuid

    Arguments:
        course (dict): course dict
        course_run_uuid (str): uuid to lookup

    Returns:
        dict: a course_run or None
    """
    try:
        course_run = [run for run in course.get('course_runs', []) if run.get('uuid') == course_run_uuid][0]
    except IndexError:
        return None
    return course_run

def is_run_restricted(run_metadata_dict):
    return run_metadata_dict.get('restriction_type') == 'restricted-b2b-enterprise'

def is_content_restricted(metadata_dict):
    """
    The given course metadata contains ONLY restricted runs, or the given run is restricted.
    """
    content_type = get_content_type(metadata_dict)
    if content_type == COURSE:
        run_dicts = metadata_dict.get('course_runs', [])
        return all(is_run_restricted(run) for run in run_dicts)
    elif content_type == COURSE_RUN:
        return is_run_restricted(metadata_dict)
    # Programs, Learner Pathways, and other content types are never considered "restricted".
    return False
