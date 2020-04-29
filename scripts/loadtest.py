"""
Shoddy script for load-testing the enterprise-catalog `get_content_metadata` API endpoint.

requirements you must pip install these before using: matplotlib, numpy, requests
"""

from collections import defaultdict
from multiprocessing import Pool
import os
from pprint import pprint
import random
import sys
import time
import uuid

import matplotlib.pyplot as plt
import numpy
import requests


# Copy your JWT payload.signature from a cookie and export into this env var.
JWT = os.environ.get('CATALOG_JWT')

# Copy your environment's catalog UUIDs and paste (one per line) into a file,
# whose absolute path you export into this env var.
CATALOG_UUIDS_FILENAME = os.environ.get('CATALOG_UUIDS_FILENAME')


def _load_lines_from_file(filename):
    clean_lines = []
    for line in open(filename):
        cleaned_line = line.strip()
        if cleaned_line:
            clean_lines.append(cleaned_line)
    return clean_lines


def _load_catalog_uuids():
    return _load_lines_from_file(CATALOG_UUIDS_FILENAME)


CATALOG_UUIDS = [uuid.UUID(uuid_str) for uuid_str in _load_catalog_uuids()]


def _headers():
    assert JWT
    return {
        "Authorization": "JWT {}".format(JWT),
    }


def _make_request(url, *args, delay_seconds=0.1):
    start = time.time()
    response = requests.get(
        url.format(*args),
        headers=_headers(),
    )
    elapsed = time.time() - start

    if response.status_code != 200:
        print(response.status_code)
        print(response.content)
        raise Exception('Got non-200 status_code')

    time.sleep(delay_seconds)

    return response.content, elapsed


def get_content_metadata(task_input):
    catalog_uuid, delay_seconds = task_input

    response_content, elapsed = _make_request(
        'https://enterprise-catalog.stage.edx.org/api/v1/enterprise-catalogs/{}/get_content_metadata.json/?traverse_pagination=1',
        catalog_uuid,
        delay_seconds=delay_seconds,
    )
    print('Got metadata for {} in {} seconds'.format(catalog_uuid, elapsed))
    return catalog_uuid, response_content, elapsed


def get_catalog_contains_content_items(task_input):
    catalog_uuid, delay_seconds, content_item_key = task_input

    response_content, elapsed = _make_request(
        'https://enterprise-catalog.stage.edx.org/api/v1/enterprise-catalogs/{}/contains_content_items.json/?course_run_ids={}',
        catalog_uuid,
        content_item_key,
        delay_seconds=delay_seconds,
    )

    print(response_content, elapsed)
    return elapsed


def get_enterprise_contains_content_items(task_input):
    enterprise_uuid, delay_seconds, content_item_key = task_input

    response_content, elapsed = _make_request(
        'https://enterprise-catalog.stage.edx.org/api/v1/enterprise-customer/{}/contains_content_items.json/?course_run_ids={}',
        enterprise_uuid,
        content_item_key,
        delay_seconds=delay_seconds,
    )

    print(response_content, elapsed)
    return elapsed


def content_metadata_loadtest(async=False, num_procs=4, number_requests=100, delay_seconds=2):
    response_times_and_sizes = []
    uuid_input = [str(random.choice(CATALOG_UUIDS)) for _ in range(number_requests)]
    delay_input = [delay_seconds for _ in range(number_requests)]
    task_input = zip(uuid_input, delay_input)

    if async:
        with Pool(processes=num_procs) as pool:
            result = pool.map_async(get_content_metadata, task_input)
            pool.close()
            pool.join()

            max_size_catalog = None
            max_size = 0
            for catalog_uuid, response_content, elapsed in result.get():
                if len(response_content) > max_size:
                    max_size = len(response_content)
                    max_size_catalog = catalog_uuid
                response_times_and_sizes.append((elapsed, len(response_content)))
            print('Biggest catalog: {}'.format(max_size_catalog))

    else:
        result = map(get_content_metadata, task_input)
        for catalog_uuid, response_content, elapsed in result:
            response_times_and_sizes.append((elapsed, len(response_content)))

    return response_times_and_sizes


def _contains_content_items_loadtest(
        request_function, primary_uuid, item_id_filename,
        async=False, num_procs=4, number_requests=100, delay_seconds=2,
        random_misses=False
):
    response_times = []

    item_ids = _load_lines_from_file(item_id_filename)

    content_item_input = [
        _perturb(random.choice(item_ids), do_nothing=not random_misses)
        for _ in range(number_requests)
    ]
    delay_input = [delay_seconds for _ in range(number_requests)]
    catalog_uuid_input = [primary_uuid for _ in range(number_requests)]
    task_input = zip(catalog_uuid_input, delay_input, content_item_input)

    if async:
        with Pool(processes=num_procs) as pool:
            result = pool.map_async(request_function, task_input)
            pool.close()
            pool.join()

            return list(result.get())

    else:
        return list(map(request_function, task_input))


def catalog_contains_content_items_loadtest(
        catalog_uuid, item_id_filename,
        async=False, num_procs=4, number_requests=100, delay_seconds=2,
        random_misses=False
):
    return _contains_content_items_loadtest(
        get_catalog_contains_content_items, catalog_uuid, item_id_filename,
        async=async, num_procs=num_procs, number_requests=number_requests, delay_seconds=delay_seconds,
        random_misses=random_misses
    )


def enterprise_contains_content_items_loadtest(
        enterprise_uuid, item_id_filename,
        async=False, num_procs=4, number_requests=100, delay_seconds=2,
        random_misses=False
):
    return _contains_content_items_loadtest(
        get_enterprise_contains_content_items, enterprise_uuid, item_id_filename,
        async=async, num_procs=num_procs, number_requests=number_requests, delay_seconds=delay_seconds,
        random_misses=random_misses
    )


def _perturb(content_id, do_nothing):
    if do_nothing:
        return content_id

    # flip a coin - if heads, also do nothing
    if random.randint(0, 100) % 2:
        return content_id

    midpoint = int(len(content_id) / 2)
    return content_id[midpoint:] + content_id[:midpoint]


def analyze_with_sizes(response_times_and_sizes):
    response_times, response_sizes = zip(*response_times_and_sizes)

    mean_response_time = sum(response_times) / len(response_times)
    corr = numpy.corrcoef(response_times, response_sizes)
    tiles = [50, 90, 99]
    percentiles = numpy.percentile(response_times, tiles)

    print('Mean response time: {}'.format(mean_response_time))
    print('Max response time: {}'.format(max(response_times)))
    print('Correlation between response size and response time: {}'.format(corr[0][1]))
    print('50th, 90th, 99th percentiles: {}'.format(percentiles))

    plt.plot(response_sizes, response_times, 'ro')
    plt.xlabel('Response size (bytes)')
    plt.ylabel('Response time (seconds)')
    plt.axis([min(response_sizes) - 1000, max(response_sizes) + 1000, 0, 3])
    plt.show()


def analyze(response_times):
    mean_response_time = sum(response_times) / len(response_times)
    tiles = [50, 90, 99]
    percentiles = numpy.percentile(response_times, tiles)

    print('Mean response time: {}'.format(mean_response_time))
    print('Max response time: {}'.format(max(response_times)))
    print('50th, 90th, 99th percentiles: {}'.format(percentiles))


if __name__ == '__main__':
    if sys.argv[1] == 'get_content_metadata':
        response_times_and_sizes = content_metadata_loadtest(
            async=False, num_procs=4, number_requests=5, delay_seconds=0.1
        )
        analyze_with_sizes(response_times_and_sizes)
    if sys.argv[1] == 'catalog_contains_content_items':
        catalog_uuid = sys.argv[2]
        content_items_filenames = sys.argv[3]
        response_times = catalog_contains_content_items_loadtest(
            catalog_uuid, content_items_filenames,
            async=False, num_procs=16, number_requests=100, delay_seconds=0.01, random_misses=True
        )
        analyze(response_times)
    if sys.argv[1] == 'enterprise_contains_content_items':
        enterprise_uuid = sys.argv[2]
        content_items_filenames = sys.argv[3]
        response_times = enterprise_contains_content_items_loadtest(
            enterprise_uuid, content_items_filenames,
            async=True, num_procs=16, number_requests=1600, delay_seconds=0.01, random_misses=True
        )
        analyze(response_times)
