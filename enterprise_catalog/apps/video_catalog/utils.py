"""
Utility functions for the video_catalog app.
"""
import logging

import requests
from django.conf import settings
from opaque_keys.edx.keys import UsageKey
from rest_framework.exceptions import ValidationError

from enterprise_catalog.apps.ai_curation.openai_client import chat_completions
from enterprise_catalog.apps.api_client.studio import StudioApiClient
from enterprise_catalog.apps.catalog.constants import COURSE_RUN
from enterprise_catalog.apps.catalog.models import ContentMetadata
from enterprise_catalog.apps.video_catalog.models import Video, VideoShortlist


logger = logging.getLogger(__name__)


def fetch_course_video_metadata(course_run_key, video_usage_key):
    """
    Fetch and store video metadata from the Studio service.

    Arguments:
        course_run_key (str): The course run key for which to fetch video metadata.
        video_usage_key (str): The video usage key for which to fetch video metadata.

    Raises:
        (DoesNotExist): If the course run key does not exist in the ContentMetadata model.
    """
    client = StudioApiClient()
    video_metadata = client.get_course_videos(course_run_key)
    for video_data in video_metadata.get('previous_uploads', []):
        video_usage_locations = client.get_video_usage_locations(course_run_key, video_data['edx_video_id'])
        for location in video_usage_locations:
            if video_usage_key in location:
                Video.objects.update_or_create(
                    edx_video_id=video_data['edx_video_id'],
                    video_usage_key=video_usage_key,
                    defaults={
                        'client_video_id': video_data['client_video_id'],
                        'json_metadata': video_data,
                        'parent_content_metadata': ContentMetadata.objects.get(
                            content_key=course_run_key, content_type=COURSE_RUN
                        )
                    }
                )


def fetch_videos():
    """
    Fetch and store video metadata for multiple course run keys.

    Arguments:
        course_keys (list): List of course run keys for which to fetch video metadata.
    """
    shortlisted_videos = VideoShortlist.objects.all()
    for video in shortlisted_videos:
        try:
            video_usage_key = UsageKey.from_string(video.video_usage_key)
        except ValueError:
            raise ValidationError('Invalid usage key')  # lint-amnesty, pylint: disable=raise-missing-from
        course_run_key = str(video_usage_key.context_key)
        fetch_course_video_metadata(course_run_key, video.video_usage_key)


def get_transcript_summary(transcript: str, max_length: int = 260) -> str:
    """
    Generate a summary of the video transcript.

    Arguments:
        transcript (str): The video transcript.
        max_length (int): The maximum length of the summary.

    Returns:
        (str): The summary of the video transcript.
    """
    messages = [
        {
            'role': 'system',
            'content': settings.SUMMARIZE_VIDEO_TRANSCRIPT_PROMPT.format(count=max_length, transcript=transcript)
        }
    ]
    return chat_completions(messages=messages, response_format='text', response_type=str)


def fetch_transcript(transcript_url: str, include_time_markings: bool = True) -> str:
    """
    Fetch the transcript from the given URL.

    Arguments:
        transcript_url (str): The URL to fetch the transcript from.
        include_time_markings (bool): Whether to include time markings in the transcript.

    Returns:
        (str): The fetched transcript.
    """
    response = requests.get(transcript_url, timeout=settings.TRANSCRIPT_FETCH_TIMEOUT)
    if include_time_markings:
        return response.text
    else:
        return ' '.join(response.json().get('text', []))


def generate_transcript_summary(video, language='en'):
    """
    Generate a summary of the video transcript.

    Arguments:
        video (Video): Video instance whose transcript to create.
        language (str): Transcript language to use for creating summary.
    """
    transcript_url = video.json_metadata['transcript_urls'].get(language)
    transcript = fetch_transcript(transcript_url, include_time_markings=False)
    return get_transcript_summary(transcript[:settings.MAX_TRANSCRIPT_LENGTH])
