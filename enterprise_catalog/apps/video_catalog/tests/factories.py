"""
Test factories for video catalog models
"""
import factory
from factory.fuzzy import FuzzyText

from enterprise_catalog.apps.catalog.tests.factories import (
    ContentMetadataFactory,
)
from enterprise_catalog.apps.video_catalog.models import (
    Video,
    VideoSkill,
    VideoTranscriptSummary,
)


class VideoFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `Video` model
    """
    class Meta:
        model = Video

    edx_video_id = FuzzyText(length=255)
    client_video_id = FuzzyText(length=255)
    video_usage_key = FuzzyText(length=150, prefix="block-v1:ACCA+FFA-F3.x+FFA1T2023+type@video+block@")
    parent_content_metadata = factory.SubFactory(ContentMetadataFactory)

    @factory.lazy_attribute
    def json_metadata(self):
        json_metadata = {
            'image_upload_url': '/video_images/course_id',
            'video_handler_url': '/videos/course_id',
            'encodings_download_url': '/video_encodings_download/course_id',
            'default_video_image_url': '/static/studio/images/video-images/default_video_image.png',
            'previous_uploads': [
                {
                    'edx_video_id': self.edx_video_id,
                    'client_video_id': self.client_video_id,
                    'created': '',
                    'courseVideoImageUrl': '/video',
                    'transcripts': [],
                    'status': 'Imported',
                    'file_size': '123',
                    'download_link': 'http:/download_video.com'
                },
                {
                    'edx_video_id': self.edx_video_id,
                    'client_video_id': self.client_video_id,
                    'created': '',
                    'courseVideoImageUrl': '',
                    'transcripts': ['en'],
                    'status': 'Ready',
                    'file_size': '123',
                    'download_link': 'http:/download_video.com'
                },
            ],
            'concurrent_upload_limit': '4',
            'video_supported_file_formats': ['.mp4', '.mov'],
            'video_upload_max_file_size': '5',
            'video_image_settings': {
                'video_image_upload_enabled': 'false',
                'max_size': '2097152',
                'min_size': '2048',
                'max_width': '1280',
                'max_height': '720',
                'supported_file_formats': {
                    '.bmp': 'image/bmp',
                    '.bmp2': 'image/x-ms-bmp',
                    '.gif': 'image/gif',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                },
            },
            'is_video_transcript_enabled': 'false',
            'active_transcript_preferences': '',
            'transcript_credentials': {},
            'transcript_available_languages': [{'language_code': 'ab', 'language_text': 'Abkhazian'}],
            'video_transcript_settings': {
                'transcript_download_handler_url': '/transcript_download/',
                'transcript_upload_handler_url': '/transcript_upload/',
                'transcript_delete_handler_url': '/transcript_delete/course_id',
                'trancript_download_file_format': 'srt',
            },
            'pagination_context': {},
        }

        return json_metadata


class VideoTranscriptSummaryFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `VideoTranscriptSummary` model
    """
    class Meta:
        model = VideoTranscriptSummary

    video = factory.SubFactory(Video)
    summary = FuzzyText(length=4096)


class VideoSkillFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `VideoSkill` model
    """
    class Meta:
        model = VideoSkill

    video = factory.SubFactory(Video)
    skill_id = FuzzyText(length=255)
    name = FuzzyText(length=255)
