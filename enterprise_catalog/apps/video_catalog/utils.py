"""
Utility functions for the video_catalog app.
"""
import logging

import requests
from django.conf import settings
from django.db import IntegrityError
from opaque_keys.edx.keys import UsageKey
from rest_framework.exceptions import ValidationError

from enterprise_catalog.apps.ai_curation.openai_client import chat_completions
from enterprise_catalog.apps.api_client.discovery import DiscoveryApiClient
from enterprise_catalog.apps.api_client.studio import StudioApiClient
from enterprise_catalog.apps.api_client.xpert_ai import chat_completion
from enterprise_catalog.apps.catalog.constants import COURSE_RUN
from enterprise_catalog.apps.catalog.models import ContentMetadata
from enterprise_catalog.apps.video_catalog.errors import (
    TranscriptSummaryMissingError,
)
from enterprise_catalog.apps.video_catalog.models import Video, VideoSkill


logger = logging.getLogger(__name__)


def fetch_course_video_metadata(course_run_key, video_usage_key, video_title):
    """
    Fetch and store video metadata from the Studio service.

    Arguments:
        course_run_key (str): The course run key for which to fetch video metadata.
        video_usage_key (str): The video usage key for which to fetch video metadata.
        video_title (str): The video title to augment into the video metadata.

    Raises:
        (DoesNotExist): If the course run key does not exist in the ContentMetadata model.
    """
    client = StudioApiClient()
    video_metadata = client.get_course_videos(course_run_key)
    for video_data in video_metadata.get('previous_uploads', []):
        video_usage_locations = client.get_video_usage_locations(course_run_key, video_data['edx_video_id'])
        for location in video_usage_locations:
            if video_usage_key in location:
                try:
                    Video.objects.update_or_create(
                        edx_video_id=video_data['edx_video_id'],
                        defaults={
                            'client_video_id': video_data['client_video_id'],
                            'json_metadata': video_data,
                            'video_usage_key': video_usage_key,
                            'title': video_title or generate_video_title(video_data['transcript_urls']),
                            'parent_content_metadata': ContentMetadata.objects.get(
                                content_key=course_run_key, content_type=COURSE_RUN
                            )
                        }
                    )
                except (ContentMetadata.DoesNotExist, IntegrityError, TranscriptSummaryMissingError) as ex:
                    logger.error(
                        '[FETCH_VIDEO_METADATA] Could not save video: Course: [%s], Video: [%s], Ex: [%s]',
                        course_run_key, video_usage_key, str(ex)
                    )


def fetch_video(shortlisted_video):
    """
    Fetch and store video metadata.

    Arguments:
        video (Video): The VideoShortlist object.
    """
    try:
        video_usage_key = UsageKey.from_string(shortlisted_video.video_usage_key)
    except ValueError as e:
        raise ValidationError('Invalid video usage key') from e
    course_run_key = str(video_usage_key.context_key)
    fetch_course_video_metadata(course_run_key, shortlisted_video.video_usage_key, shortlisted_video.title)


def store_video_skills(video):
    """
    Fetch and store video skills for a video.

    Arguments:
        video (Video): The Video object.
    """
    try:
        video_skills = DiscoveryApiClient().get_video_skills(video.video_usage_key)
        for skill in video_skills:
            VideoSkill.objects.update_or_create(
                video=video,
                skill_id=skill.get('id'),
                name=skill.get('name'),
            )
    except Exception as exc:
        logger.exception(f'Could not retrieve and store video skills {exc}')
        raise exc


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
    return chat_completions(messages=messages, response_format='text')


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


def generate_transcript_summary(transcript_urls, language='en'):
    """
    Generate a summary of the video transcript.

    Arguments:
        transcript_urls (dict): Transcript URLs. Keys are language codes, values are URLs.
        language (str): Transcript language to use for creating summary.
    """
    # If no transcript URL is available for the given language, return None
    if (transcript_url := transcript_urls.get(language)) is None:
        return None

    transcript = fetch_transcript(transcript_url, include_time_markings=False)
    return get_transcript_summary(transcript[:settings.MAX_TRANSCRIPT_LENGTH])


def generate_video_title(transcript_urls, language='en', max_length: int = 60) -> str:
    """
    Generate a title for the video from its transcript.

    Arguments:
        transcript_urls (dict): Transcript URLs. Keys are language codes, values are URLs.
        language (str): Title language.

    Returns:
        (str): The title of the video.
    """
    # If transcript summary is not available for the given language, return an empty string
    if (transcript_summary := generate_transcript_summary(transcript_urls, language)) is None:
        raise TranscriptSummaryMissingError

    messages = [
        {
            'role': 'user',
            'content': settings.GENERATE_VIDEO_TITLE_USER_ROLE_MESSAGE.format(
                max_length=max_length,
                transcript_summary=transcript_summary
            )
        }
    ]
    return chat_completion(
        system_message=settings.GENERATE_VIDEO_TITLE_SYSTEM_ROLE_MESSAGE,
        user_messages=messages
    )
