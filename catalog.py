"""
To run from app-shell:
./manage.py shell < catalog.py
"""

from enterprise_catalog.apps.catalog.models import *
from collections import *
from pprint import pprint

def get_programs_by_course():
    """ Prefetch course id -> program id mapping. """
    program_membership_by_course_key = defaultdict(set)
    programs = ContentMetadata.objects.filter(content_type=PROGRAM).prefetch_related('associated_content_metadata')
    for prog in programs:
        for course in prog.associated_content_metadata.all():
            program_membership_by_course_key[course.content_key].add(prog.content_key)
    return program_membership_by_course_key


def get_catalog_by_query():
    """ Prefetch catalog uuids by catalogquery.id mapping """
    catalog_uuid_by_query_id = defaultdict(set)
    for catalog in EnterpriseCatalog.objects.iterator():
        catalog_uuid_by_query_id[catalog.catalog_query_id].add(catalog.uuid)
    return catalog_uuid_by_query_id


def iterate_membership():
    all_memberships = ContentMetadataToQueries.objects.select_related(
        'catalog_query', 'content_metadata'
    ).iterator()
    for membership in all_memberships:
        metadata = membership.content_metadata
        catalog_query = membership.catalog_query
        print('Metadata: {}'.format(metadata.content_key))
        print('Catalog Query: {}'.format(catalog_query.uuid))


def test():
    progs_by_course = get_programs_by_course()
    catalog_by_query_id = get_catalog_by_query()
    pprint(progs_by_course)
    pprint(catalog_by_query_id)
    iterate_membership()


test()
