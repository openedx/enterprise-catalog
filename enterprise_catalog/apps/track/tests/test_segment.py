from unittest import mock

from django.test import override_settings

from enterprise_catalog.apps.track.segment import track_event


MOCK_LMS_USER_ID = 'lms_user_id'
MOCK_EVENT_NAME = 'mock.event.name'


@override_settings(SEGMENT_KEY=None)
@mock.patch('enterprise_catalog.apps.track.segment.logger', return_value=mock.MagicMock())
def test_track_event_no_segment_key(mock_logger):
    track_event(MOCK_LMS_USER_ID, MOCK_EVENT_NAME, {})
    mock_logger.warning.assert_called_with(
        "Segment event %s for user_id %s not tracked because SEGMENT_KEY not set", MOCK_EVENT_NAME, MOCK_LMS_USER_ID
    )


@override_settings(SEGMENT_KEY='123')
@mock.patch('enterprise_catalog.apps.track.segment.logger', return_value=mock.MagicMock())
@mock.patch('enterprise_catalog.apps.track.segment.analytics', return_value=mock.MagicMock())
def test_track_event_catches_exceptions(mock_analytics, mock_logger):
    mock_analytics.track.side_effect = Exception('Something went wrong')
    track_event(MOCK_LMS_USER_ID, MOCK_EVENT_NAME, {})
    mock_logger.exception.assert_called()
