""" Test Util for catalog models. """

import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
)
from enterprise_catalog.apps.catalog.tests import factories


@ddt.ddt
class TestUtils(TestCase):
    """
    Test Util for testing Catalog Models
    """

    def setup_scaffolding(
        self,
        create_catalog_query,
        create_content_metadata=None,
        create_restricted_courses=None,
        create_restricted_run_allowed_for_restricted_course=None,
    ):
        """
        Helper function to create an arbitrary number of CatalogQuery, ContentMetadata,
        RestrictedCourseMetadata, and RestrictedRunAllowedForRestrictedCourse objects for testing
        purposes.
        """
        catalog_queries = {
            cq_uuid: factories.CatalogQueryFactory(
                uuid=cq_uuid,
                content_filter=cq_info['content_filter'] | {'force_unique': cq_uuid},
            ) for cq_uuid, cq_info in create_catalog_query.items()
        }
        content_metadata = {}
        create_content_metadata = create_content_metadata or {}
        for course_key, course_info in create_content_metadata.items():
            course = factories.ContentMetadataFactory(
                content_key=course_key,
                content_type=COURSE,
                _json_metadata=course_info['json_metadata'],
            )
            content_metadata.update({course_key: course})
            if cq_uuid := course_info['associate_with_catalog_query']:
                course.catalog_queries.set([catalog_queries[cq_uuid]])
            for run_key, run_info in course_info['create_runs'].items():
                run = factories.ContentMetadataFactory(
                    content_key=run_key,
                    parent_content_key=course_key,
                    content_type=COURSE_RUN,
                )
                if run_info['is_restricted']:
                    # pylint: disable=protected-access
                    run._json_metadata.update({'restriction_type': 'custom-b2b-enterprise'})
                    run.save()
                content_metadata.update({run_key: run})
        restricted_courses = {
            id: factories.RestrictedCourseMetadataFactory(
                id=id,
                content_key=restricted_course_info['content_key'],
                unrestricted_parent=content_metadata[restricted_course_info['content_key']],
                catalog_query=catalog_queries[restricted_course_info['catalog_query']],
                _json_metadata=restricted_course_info['json_metadata'],
            ) for id, restricted_course_info in create_restricted_courses.items()
        } if create_restricted_courses else {}
        for mapping_info in create_restricted_run_allowed_for_restricted_course or []:
            factories.RestrictedRunAllowedForRestrictedCourseFactory(
                course=restricted_courses[mapping_info['course']],
                run=content_metadata[mapping_info['run']],
            )
        main_catalog = factories.EnterpriseCatalogFactory(
            catalog_query=catalog_queries['11111111-1111-1111-1111-111111111111'],
        )
        return main_catalog, catalog_queries, content_metadata, restricted_courses
