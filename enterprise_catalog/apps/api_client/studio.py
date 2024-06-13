from .base_oauth import BaseOAuthClient
from .constants import STUDIO_API_COURSE_VIDEOS_ENDPOINT


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
