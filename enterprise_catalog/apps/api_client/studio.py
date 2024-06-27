from .base_oauth import BaseOAuthClient
from .constants import (
    STUDIO_API_COURSE_VIDEOS_ENDPOINT,
    STUDIO_API_VIDEOS_LOCATION_ENDPOINT,
)


class StudioApiClient(BaseOAuthClient):
    """
    API client to make calls to edx-enterprise API endpoints.
    """

    def get_course_videos(self, course_run_key):
        """
        Retrieve course video metadata for the given course.

        Arguments:
            course_run_key (str): The course run key for which to retrieve video metadata.

        Returns:
            (dict): Dictionary containing course video metadata.
        """
        return self.client.get(
            STUDIO_API_COURSE_VIDEOS_ENDPOINT.format(course_run_key=course_run_key),
        ).json()

    def get_video_usage_locations(self, course_run_key, edx_video_id):
        """
        Retrieve course video locations for the given course run and edx video id.

        Arguments:
            course_run_key (str): The course run key for which to retrieve video metadata.
            edx_video_id (str): The edx video id for which to retrieve video metadata.

        Returns:
            (list): List of course video locations.
        """
        locations = self.client.get(
            STUDIO_API_VIDEOS_LOCATION_ENDPOINT.format(course_run_key=course_run_key, edx_video_id=edx_video_id),
        ).json().get('usage_locations', [])

        return ([location['url'] for location in locations]) if locations else []
