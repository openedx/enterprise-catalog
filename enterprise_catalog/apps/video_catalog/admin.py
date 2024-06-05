"""
Admin for video catalog models.
"""
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from enterprise_catalog.apps.video_catalog.models import (
    Video,
    VideoTranscriptSummary,
)


@admin.register(VideoTranscriptSummary)
class VideoTranscriptSummaryAdmin(SimpleHistoryAdmin):
    """
    Django admin for VideoTranscriptSummary.
    """
    list_display = ('id', 'created', 'modified', )
    search_fields = ('id', )


@admin.register(Video)
class VideoAdmin(SimpleHistoryAdmin):
    """
    Django admin for Video.
    """
    list_display = ('edx_video_id', 'client_video_id', 'created', 'modified', )
    search_fields = ('edx_video_id', 'client_video_id', )
