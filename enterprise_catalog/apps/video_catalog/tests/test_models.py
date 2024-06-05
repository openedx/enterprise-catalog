"""
Tests for video catalog models
"""

import ddt
from django.test import TestCase

from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)
from enterprise_catalog.apps.video_catalog.tests.factories import (
    VideoFactory,
    VideoTranscriptSummaryFactory,
)


@ddt.ddt
class TestVideoModels(TestCase):
    """
    Video catalog models tests
    """

    def test_video(self):
        """
        Ensure that the video and parent course content metadata relationship is correct.
        """
        content_metadata = ContentMetadataFactory(content_type=COURSE)
        course_video = VideoFactory(parent_content_metadata=content_metadata)
        self.assertEqual(course_video.parent_content_metadata.content_key, content_metadata.content_key)

    def test_video_transcript_summary(self):
        """
        Ensure that the video transcript summary and video relationship is correct.
        """
        course_video = VideoFactory()
        video_transcript_summary = VideoTranscriptSummaryFactory(video=course_video)
        self.assertEqual(course_video.summary_transcripts.first().summary, video_transcript_summary.summary)
