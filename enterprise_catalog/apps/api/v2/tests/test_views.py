import ddt

from enterprise_catalog.apps.api.v1.tests.mixins import APITestMixin
from enterprise_catalog.apps.catalog.constants import (
    COURSE,
    COURSE_RUN,
)
from enterprise_catalog.apps.catalog.models import (
    ContentMetadata,
)
from enterprise_catalog.apps.catalog.tests.factories import (
    CatalogQueryFactory,
    ContentMetadataFactory,
    EnterpriseCatalogFactory,
    RestrictedCourseMetadataFactory,
    RestrictedRunAllowedForRestrictedCourseFactory
)


@ddt.ddt
class EnterpriseCatalogGetContentMetadataTests(APITestMixin):
    """
    Tests on the get_content_metadata endpoint
    """

    def setUp(self):
        super().setUp()
        # Set up catalog.has_learner_access permissions
        self.set_up_catalog_learner()
        self.enterprise_catalog = EnterpriseCatalogFactory(enterprise_uuid=self.enterprise_uuid)
        self.enterprise_catalog.catalog_query.save()

        # Delete any existing ContentMetadata records.
        ContentMetadata.objects.all().delete()

    def _create_objects_and_relationships(
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
            cq_uuid: CatalogQueryFactory(
                uuid=cq_uuid,
                content_filter=cq_info['content_filter'] | {'force_unique': cq_uuid},
            ) for cq_uuid, cq_info in create_catalog_query.items()
        }
        content_metadata = {}
        create_content_metadata = create_content_metadata or {}
        for course_key, course_info in create_content_metadata.items():
            course = ContentMetadataFactory(
                content_key=course_key,
                content_type=COURSE,
                _json_metadata=course_info['json_metadata'],
            )
            content_metadata.update({course_key: course})
            if cq_uuid := course_info['associate_with_catalog_query']:
                course.catalog_queries.set([catalog_queries[cq_uuid]])
            for run_key, run_info in course_info['create_runs'].items():
                run = ContentMetadataFactory(
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
            id: RestrictedCourseMetadataFactory(
                id=id,
                content_key=restricted_course_info['content_key'],
                unrestricted_parent=content_metadata[restricted_course_info['content_key']],
                catalog_query=catalog_queries[restricted_course_info['catalog_query']],
                _json_metadata=restricted_course_info['json_metadata'],
            ) for id, restricted_course_info in create_restricted_courses.items()
        } if create_restricted_courses else {}
        for mapping_info in create_restricted_run_allowed_for_restricted_course or []:
            RestrictedRunAllowedForRestrictedCourseFactory(
                course=restricted_courses[mapping_info['course']],
                run=content_metadata[mapping_info['run']],
            )
        main_catalog = EnterpriseCatalogFactory(
            catalog_query=catalog_queries['11111111-1111-1111-1111-111111111111'],
        )
        return main_catalog, catalog_queries, content_metadata, restricted_courses

    @ddt.data(
        # Create a course with both an unrestricted (run1) and restricted run (run2), and the restricted run is allowed
        # by the CatalogQuery.
        {
            'create_catalog_query': {
                '11111111-1111-1111-1111-111111111111': {
                    'content_filter': {
                        'restricted_runs_allowed': {
                            'course:edX+course': [
                                'course-v1:edX+course+run2',
                            ],
                        },
                    },
                },
            },
            'create_content_metadata': {
                'edX+course': {
                    'create_runs': {
                        'course-v1:edX+course+run1': {'is_restricted': False},
                        'course-v1:edX+course+run2': {'is_restricted': True},
                    },
                    'json_metadata': {'foobar': 'base metadata'},
                    'associate_with_catalog_query': '11111111-1111-1111-1111-111111111111',
                },
            },
            'create_restricted_courses': {
                1: {
                    'content_key': 'edX+course',
                    'catalog_query': '11111111-1111-1111-1111-111111111111',
                    'json_metadata': {'foobar': 'override metadata'},
                },
            },
            'create_restricted_run_allowed_for_restricted_course': [
                {'course': 1, 'run': 'course-v1:edX+course+run2'},
            ],
        },
    )
    @ddt.unpack
    def test_get_content_metadata_combined(
        self,
        create_catalog_query,
        create_content_metadata=None,
        create_restricted_courses=None,
        create_restricted_run_allowed_for_restricted_course=None,
    ):
        """
        Test the get_content_metadata endpoint to verify that restricted content is properly
        handled, both for restricted and unrestricted course runs
        """
        main_catalog, catalog_queries, content_metadata, restricted_courses = self._create_objects_and_relationships(
            create_catalog_query,
            create_content_metadata,
            create_restricted_courses,
            create_restricted_run_allowed_for_restricted_course,
        )

        # Test unrestricted content retrieval with `include_restricted=False`
        response_unrestricted = main_catalog.get_matching_content(
            ['edX+course'],
            include_restricted=False
        )
        self.assertTrue(len(response_unrestricted) > 0)
        self.assertIn('edX+course', [item.content_key for item in response_unrestricted])

    @ddt.data(
        # Create a course with ONLY a restricted run (run1), and the restricted run is allowed by the CatalogQuery.
        # This type of course has colloquially been referred to as "Unicorn".
        {
            'create_catalog_query': {
                '11111111-1111-1111-1111-111111111111': {
                    'content_filter': {
                        'restricted_runs_allowed': {
                            'course:edX+course': [
                                'course-v1:edX+course+run2',
                            ],
                        },
                    },
                },
            },
            'create_content_metadata': {
                'edX+course': {
                    'create_runs': {
                        # The only run is a restricted run.
                        'course-v1:edX+course+run1': {'is_restricted': True},
                    },
                    'json_metadata': {'foobar': 'base metadata'},
                    'associate_with_catalog_query': '11111111-1111-1111-1111-111111111111',
                },
            },
            'create_restricted_courses': {
                1: {
                    'content_key': 'edX+course',
                    'catalog_query': '11111111-1111-1111-1111-111111111111',
                    'json_metadata': {'foobar': 'override metadata'},
                },
            },
            'create_restricted_run_allowed_for_restricted_course': [
                {'course': 1, 'run': 'course-v1:edX+course+run1'},
            ],
        },
    )
    @ddt.unpack
    def test_get_content_metadata_restricted(
        self,
        create_catalog_query,
        create_content_metadata=None,
        create_restricted_courses=None,
        create_restricted_run_allowed_for_restricted_course=None,
    ):
        """
        Test the get_content_metadata endpoint to verify that restricted content is properly
        handled, for restricted course runs
        """
        main_catalog, catalog_queries, content_metadata, restricted_courses = self._create_objects_and_relationships(
            create_catalog_query,
            create_content_metadata,
            create_restricted_courses,
            create_restricted_run_allowed_for_restricted_course,
        )

        # Test restricted content is retrieved when `include_restricted=False`
        response_restricted = main_catalog.get_matching_content(
            ['edX+course'],
            include_restricted=False
        )
        print(f"Response Restricted (should be empty): {response_restricted}")
        self.assertEqual(len(response_restricted), 1)
        self.assertIn('edX+course', [item.content_key for item in response_restricted])

        # Test restricted content IS retrieved when `include_restricted=True`
        response_with_restricted = main_catalog.get_matching_content(
            ['edX+course'],
            include_restricted=True
        )
        print(f"Response with Restricted Content: {response_with_restricted}")  # Debugging output
        self.assertTrue(len(response_with_restricted) > 0)
        self.assertIn('edX+course', [item.content_key for item in response_with_restricted])

        # Test that the fully restricted course run is NOT retrieved with `include_restricted=False`
        response_run_restricted_false = main_catalog.get_matching_content(
            ['course-v1:edX+course+run1'],
            include_restricted=False
        )
        self.assertEqual(len(response_run_restricted_false), 0)

        # Test that the fully restricted course run IS retrieved with `include_restricted=True`
        response_run_restricted_true = main_catalog.get_matching_content(
            ['course-v1:edX+course+run1'],
            include_restricted=True
        )
        self.assertTrue(len(response_run_restricted_true) > 0)
        self.assertIn('edX+course',
                      [item.content_key for item in response_run_restricted_true])
