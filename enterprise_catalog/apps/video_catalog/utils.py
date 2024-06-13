"""
Utility functions for the video_catalog app.
"""
from enterprise_catalog.apps.api_client.studio import StudioApiClient
from enterprise_catalog.apps.catalog.constants import COURSE, COURSE_RUN
from enterprise_catalog.apps.catalog.models import ContentMetadata
from enterprise_catalog.apps.video_catalog.models import Video


def fetch_course_video_metadata(course_run_key):
    """
    Fetch and store video metadata from the Studio service.

    Arguments:
        course_run_key (str): The course run key for which to fetch video metadata.

    Raises:
        (DoesNotExist): If the course run key does not exist in the ContentMetadata model.
    """
    client = StudioApiClient()
    video_metadata = client.get_course_videos(course_run_key)
    for video_data in video_metadata.get('previous_uploads', []):
        Video.objects.update_or_create(
            edx_video_id=video_data['edx_video_id'],
            defaults={
                'client_video_id': video_data['client_video_id'],
                'json_metadata': video_data,
                'parent_content_metadata': ContentMetadata.objects.get(
                    content_key=course_run_key, content_type=COURSE_RUN
                )
            }
        )


def fetch_videos(course_keys):
    """
    Fetch and store video metadata for multiple course run keys.

    Arguments:
        course_keys (list): List of course run keys for which to fetch video metadata.
    """
    courses = ContentMetadata.objects.filter(content_key__in=course_keys, content_type=COURSE)
    for course in courses:
        course_run = course.get_child_records(course).first()
        if course_run:
            fetch_course_video_metadata(course_run.content_key)
