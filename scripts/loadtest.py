"""
Shoddy script for load-testing the enterprise-catalog `get_content_metadata` API endpoint.

requirements (you must pip install these before using):
matplotlib==3.0.3
numpy==1.18.3
requests==2.23.0
"""

from collections import defaultdict
from multiprocessing import Pool
import os
from pprint import pprint
import random
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


def _load_catalog_uuids():
    uuids = []
    for line in open(CATALOG_UUIDS_FILENAME):
        cleaned_line = line.strip()
        if cleaned_line:
            uuids.append(cleaned_line)
    return uuids


CATALOG_UUIDS = [uuid.UUID(uuid_str) for uuid_str in _load_catalog_uuids()]


def _headers():
    assert JWT
    return {
        "Authorization": "JWT {}".format(JWT),
    }


def get_content_metadata(task_input):
    catalog_uuid, delay_seconds = task_input
    print('Getting metadata for {}'.format(catalog_uuid))
    
    start = time.time()
    response = requests.get(
        'https://enterprise-catalog.stage.edx.org/api/v1/enterprise-catalogs/{}/get_content_metadata/'.format(catalog_uuid),
        headers=_headers(),
    )
    if response.status_code != 200:
        print(response.status_code)
        print(response.content)
        raise Exception('Got non-200 status_code')

    elapsed = time.time() - start
    
    time.sleep(delay_seconds)
    
    return catalog_uuid, response, elapsed


def content_metadata_loadtest(num_procs=4, number_requests=100, delay_seconds=2):
    data_by_catalog_uuid = defaultdict(list)
    response_times_and_sizes = []
    uuid_input = [str(random.choice(CATALOG_UUIDS)) for _ in range(number_requests)]
    delay_input = [delay_seconds for _ in range(number_requests)]
    task_input = zip(uuid_input, delay_input)

    # with Pool(processes=num_procs) as pool:
    #     result = pool.map_async(get_content_metadata, task_input)
    #     pool.close()
    #     pool.join()

    result = map(get_content_metadata, task_input)
    for catalog_uuid, response, elapsed in result:
        response_times_and_sizes.append((elapsed, len(response.content)))

    return response_times_and_sizes


def analyze(response_times_and_sizes):
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


if __name__ == '__main__':
    response_times_and_sizes = content_metadata_loadtest(num_procs=4, number_requests=200, delay_seconds=0.1)
    analyze(response_times_and_sizes)
