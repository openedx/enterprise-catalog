"""
Tests for video catalog utils.
"""
from unittest import mock
from uuid import uuid4

from django.conf import settings
from django.test import TestCase, override_settings

from enterprise_catalog.apps.catalog.constants import COURSE_RUN
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)
from enterprise_catalog.apps.video_catalog.errors import (
    TranscriptSummaryMissingError,
)
from enterprise_catalog.apps.video_catalog.models import Video
from enterprise_catalog.apps.video_catalog.tests.factories import VideoFactory
from enterprise_catalog.apps.video_catalog.utils import (
    fetch_course_video_metadata,
    generate_video_title,
)


@override_settings(
    GENERATE_VIDEO_TITLE_SYSTEM_ROLE_MESSAGE='You are an expert video title generator.',
    GENERATE_VIDEO_TITLE_USER_ROLE_MESSAGE='{transcript_summary} {max_length}',
)
class GenerateVideoTitleTests(TestCase):
    """
    Tests for the generate_video_title utility function.
    """

    @mock.patch('enterprise_catalog.apps.video_catalog.utils.chat_completion')
    @mock.patch('enterprise_catalog.apps.video_catalog.utils.generate_transcript_summary')
    def test_generate_video_title_success(self, mock_generate_summary, mock_chat_completion):
        """
        Verify generate_video_title calls dependencies and returns expected title.
        """
        video = VideoFactory()
        mock_transcript_urls = video.json_metadata.get('transcript_urls', {'en': 'http://example.com/transcript.sjson'})
        mock_summary = "This is a test summary."
        mock_title = "Generated Test Title"

        mock_generate_summary.return_value = mock_summary
        mock_chat_completion.return_value = mock_title
        result_title = generate_video_title(mock_transcript_urls)

        # Check that generate_transcript_summary was called correctly
        mock_generate_summary.assert_called_once_with(mock_transcript_urls, 'en')

        # Check that chat_completion was called correctly
        expected_user_message = settings.GENERATE_VIDEO_TITLE_USER_ROLE_MESSAGE.format(
            transcript_summary=mock_summary,
            max_length=60
        )
        mock_chat_completion.assert_called_once_with(
            system_message=settings.GENERATE_VIDEO_TITLE_SYSTEM_ROLE_MESSAGE,
            user_messages=[{'role': 'user', 'content': expected_user_message}]
        )

        # Check the final result
        self.assertEqual(result_title, mock_title)

    @mock.patch('enterprise_catalog.apps.video_catalog.utils.chat_completion')
    @mock.patch('enterprise_catalog.apps.video_catalog.utils.generate_transcript_summary')
    def test_generate_video_title_no_summary(self, mock_generate_summary, mock_chat_completion):
        """
        Verify generate_video_title raises TranscriptSummaryMissingError
        if transcript summary is None.
        """
        mock_transcript_urls = {'en': 'http://example.com/transcript.sjson'}

        # Mock generate_transcript_summary to return None
        mock_generate_summary.return_value = None

        with self.assertRaises(TranscriptSummaryMissingError):
            generate_video_title(mock_transcript_urls)

        # Check that generate_transcript_summary was called
        mock_generate_summary.assert_called_once_with(mock_transcript_urls, 'en')
        # Check that chat_completion was NOT called
        mock_chat_completion.assert_not_called()


class FetchCourseVideoMetadataTests(TestCase):
    """
    Tests for the fetch_course_video_metadata utility function.
    """

    def setUp(self):
        super().setUp()
        self.course_run_key = "course-v1:TestOrg+TestCourse+TestRun"
        self.video_usage_key = f"block-v1:TestOrg+TestCourse+TestRun+type@video+block@{uuid4().hex}"
        self.edx_video_id = "vid-" + uuid4().hex
        self.client_video_id = "client-vid.mp4"
        self.mock_transcript_urls = {'en': 'http://example.com/transcript_en.sjson'}

        self.mock_video_data = {
            'edx_video_id': self.edx_video_id,
            'client_video_id': self.client_video_id,
            'status': 'Ready',
            'transcript_urls': self.mock_transcript_urls,
        }
        self.mock_studio_response = {
            'previous_uploads': [self.mock_video_data]
        }
        self.mock_usage_locations = [f"http://studio/jump_to/{self.video_usage_key}"]

        # Create parent ContentMetadata
        self.parent_metadata = ContentMetadataFactory(
            content_key=self.course_run_key,
            content_type=COURSE_RUN
        )

    @mock.patch('enterprise_catalog.apps.video_catalog.utils.generate_video_title')
    @mock.patch('enterprise_catalog.apps.video_catalog.utils.Video.objects.update_or_create')
    @mock.patch('enterprise_catalog.apps.video_catalog.utils.ContentMetadata.objects.get')
    @mock.patch('enterprise_catalog.apps.video_catalog.utils.StudioApiClient')
    def test_fetch_success_generate_title(
        self, mock_studio_client_cls, mock_cm_get, mock_video_update_or_create, mock_generate_title
    ):
        """
        Verify successful fetching and storing, including title generation when no title is provided.
        """
        mock_client_instance = mock_studio_client_cls.return_value
        mock_client_instance.get_course_videos.return_value = self.mock_studio_response
        mock_client_instance.get_video_usage_locations.return_value = self.mock_usage_locations
        mock_cm_get.return_value = self.parent_metadata
        # The Video instance returned by update_or_create is not used further in this path
        mock_video_update_or_create.return_value = (mock.Mock(spec=Video), True)
        generated_title = "Generated Title"
        mock_generate_title.return_value = generated_title

        # Call fetch_course_video_metadata with an empty video_title, expecting title generation
        fetch_course_video_metadata(self.course_run_key, self.video_usage_key, "")

        # Verify generate_video_title was called with the transcript_urls from the video data
        mock_generate_title.assert_called_once_with(self.mock_transcript_urls)

        # Verify Video.objects.update_or_create was called with the generated title
        mock_video_update_or_create.assert_called_once_with(
            edx_video_id=self.edx_video_id,
            defaults={
                'client_video_id': self.client_video_id,
                'json_metadata': self.mock_video_data,
                'video_usage_key': self.video_usage_key,
                'title': generated_title,  # Title should be the generated one
                'parent_content_metadata': self.parent_metadata
            }
        )
