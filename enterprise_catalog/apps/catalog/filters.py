"""
Utility functions for catalog query filtering without elasticsearch
"""
import logging


logger = logging.getLogger(__name__)


SUPPORTED_FILTER_COMPARISONS = [
    'exact',
    'not',
    'exclude',
    'gt',
    'gte',
    'lt',
    'lte',
]


class QueryFilterException(Exception):
    """
    An exception for content catalog query filtering
    """


def fix_common_query_key_mistakes(raw_query_key):
    """
    In production many queries have odd typos
    which seem to have been copypasta-proliferated
    """
    corrections_for_typos = {
        'aggregation_key': [
            'aggregration__key',
            'aggregation__key',
        ],
        'org__exclude': [
            'org__exempt',
        ],
    }
    for correction, typos in corrections_for_typos.items():
        if raw_query_key in typos:
            return correction
    return raw_query_key


def extract_field_and_comparison_kind(raw_query_key):
    """
    Taking an query key, extra the content_metadata
    field name and the kind of comparison matching
    should be used.
    """
    field = None
    # comparison_kind defaults to "exact match"
    comparison_kind = 'exact'
    split_query_key = raw_query_key.split("__")
    if len(split_query_key) == 2:
        field, comparison_kind = split_query_key
    elif len(split_query_key) > 2:
        raise QueryFilterException(f'invalid syntax "{raw_query_key}"')
    else:
        field = raw_query_key
    if comparison_kind not in SUPPORTED_FILTER_COMPARISONS:
        raise QueryFilterException(f'unsupported action "{comparison_kind}" from query key "{raw_query_key}"')
    logger.debug(f'extract_field_and_action "{raw_query_key}" -> {field}, {comparison_kind}')
    return field, comparison_kind


def field_comparison(query_value, content_value, comparison_kind):
    """
    compre the fields based on the comparison kind
    python 3.10 has match (like switch)
    """
    if comparison_kind == 'exact':
        return content_value == query_value
    elif comparison_kind == 'not':
        return content_value != query_value
    elif comparison_kind == 'exclude':
        return content_value != query_value
    elif comparison_kind == 'gt':
        return float(content_value) > float(query_value)
    elif comparison_kind == 'gte':
        return float(content_value) >= float(query_value)
    elif comparison_kind == 'lt':
        return float(content_value) < float(query_value)
    elif comparison_kind == 'lte':
        return float(content_value) <= float(query_value)
    else:
        raise QueryFilterException(f'invalid comparison kind "{comparison_kind}"')


def does_query_match_content(query_dict, content_metadata_dict):
    """
    Evaluate a query and a content_metadata object to determine
    if the given content_metadata and query match.
    This is meant to partially emulate Django FieldLookups
    for dictionaries rather than querysets.
    https://docs.djangoproject.com/en/4.2/ref/models/querysets/#field-lookups
    """
    results = {}
    for raw_query_key, query_value in query_dict.items():

        query_key = fix_common_query_key_mistakes(raw_query_key)
        field, comparison_kind = extract_field_and_comparison_kind(query_key)

        if comparison_kind not in SUPPORTED_FILTER_COMPARISONS:
            raise QueryFilterException(
                f'unsupported comparison_kind "{comparison_kind}" '
                f'from query key "{raw_query_key}"'
            )

        content_value = content_metadata_dict.get(field)
        logger.debug(f'{query_key}, {field} -> {query_value}, {content_value}')

        field_result = False
        if isinstance(query_value, list):
            field_results = []
            for query_value_item in query_value:
                this_field_result = field_comparison(query_value_item, content_value, comparison_kind)
                logger.debug(f'{query_value_item}, {content_value}, {comparison_kind} -> {this_field_result}')
                field_results.append(this_field_result)
            # "exact" here means "IN" as in "is edx+demo IN ['edx+demo', 'mit+demo']"
            if comparison_kind == 'exact':
                field_result = any(field_results)
            # else here means "NOT IN"
            else:
                field_result = all(field_results)
        else:
            field_result = field_comparison(query_value, content_value, comparison_kind)

        logger.debug(f'{query_key}, {field} {comparison_kind} -> {query_value}, {content_value}, {field_result}')
        results[field] = field_result
    logger.debug(results)
    return all(results.values())
