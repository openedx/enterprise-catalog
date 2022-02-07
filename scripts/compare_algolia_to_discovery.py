import logging
import requests

from django.conf import settings

from enterprise_catalog.apps.api.v1 import export_utils
from enterprise_catalog.apps.catalog.algolia_utils import (
    get_initialized_algolia_client,
)


"""
1. setup enterprise_catalog/settings/private.py
2. cat scripts/compare_algolia_to_discovery.py | ./manage.py shell
3. pull course key content_metadata from read replica
"""

data = { 
	'grant_type': 'client_credentials',
	'client_id': settings.EDX_CLIENT_ID,
	'client_secret': settings.EDX_CLIENT_SECRET,
	'token_type': 'jwt'
}

r = requests.post('https://api.edx.org/oauth2/v1/access_token?', data=data)

access_token = r.json()['access_token']
headers = {'Authorization': f'JWT {access_token}'}


algolia_set = set()

algolia_client = get_initialized_algolia_client()
search_options = {'facetFilters': [['enterprise_catalog_query_titles:A la carte']], 'attributesToRetrieve': ['title', 'key', 'content_type', 'partners', 'advertised_course_run', 'programs', 'program_titles', 'level_type', 'language', 'short_description', 'subjects', 'aggregation_key', 'skills', 'first_enrollable_paid_seat_price', 'marketing_url', 'outcome', 'prerequisites_raw', 'program_type', 'subtitle', 'course_keys'], 'hitsPerPage': 100, 'page': 0}
algoliaQuery = ''

print("loading algolia data...")
page = algolia_client.algolia_index.search(algoliaQuery, search_options)
while len(page['hits']) > 0:
	for hit in page.get('hits', []):
		if hit.get('content_type') != 'course':
			continue
		key = hit['aggregation_key'].replace('course:', '')
		algolia_set.add(key)
	search_options['page'] = search_options['page'] + 1
	page = algolia_client.algolia_index.search(algoliaQuery, search_options)
print(f'found {len(algolia_set)} algolia course keys')

discovery_set = set()

discovery_url = 'https://discovery.edx.org/api/v1/search/all/?content_type=course&availability=Current&availability=Starting+Soon&availability=Upcoming&partner=edx&level_type=Introductory&level_type=Intermediate&level_type=Advanced&status=published&org__exclude=StanfordOnline&org__exclude=PennX'

print("loading discovery data...")
while discovery_url:
	r = requests.get(discovery_url, headers=headers)
	discovery_url = r.json()['next']
	for result in r.json()['results']:
		if result.get('content_type') != 'course':
			continue
		key = result['key']
		discovery_set.add(key)
print(f'found {len(discovery_set)} discovery course keys')

print("\n\n\n\n")

not_found_in_algolia = set()
for key in discovery_set:
	if not key in algolia_set:
		not_found_in_algolia.add(key)
print('in disocvery, not in algolia:')
print(not_found_in_algolia)

print("\n\n\n\n")

not_found_in_discovery = set()
for key in algolia_set:
	if not key in discovery_set:
		not_found_in_discovery.add(key)
print('in algolia, not in discovery:')
print(not_found_in_discovery)

print("\n\n\n\n")
