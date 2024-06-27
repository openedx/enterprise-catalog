"""
Admin for video catalog models.
"""
from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from enterprise_catalog.apps.video_catalog.models import (
    Video,
    VideoShortlist,
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


class VideoShortlistResource(resources.ModelResource):

    class Meta:
        model = VideoShortlist
        import_id_fields = ('video_usage_key',)
        fields = ('video_usage_key',)


@admin.register(VideoShortlist)
class VideoShortlistAdmin(ImportExportModelAdmin):
    """
    Django admin for VideoShortlist.
    """
    resource_classes = [VideoShortlistResource]
    list_display = ('video_usage_key',)
    search_fields = ('video_usage_key',)
