"""
Admin for video catalog models.
"""
from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.tmp_storages import CacheStorage
from simple_history.admin import SimpleHistoryAdmin

from enterprise_catalog.apps.video_catalog.models import (
    Video,
    VideoShortlist,
    VideoSkill,
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
    list_display = ('edx_video_id', 'client_video_id', 'video_usage_key', 'created', 'modified', )
    search_fields = ('edx_video_id', 'client_video_id', )
    raw_id_fields = ('parent_content_metadata', )


@admin.register(VideoSkill)
class VideoSkillAdmin(SimpleHistoryAdmin):
    """
    Django admin for VideoSkill.
    """
    list_display = ('skill_id', 'name', 'created', 'modified',)
    search_fields = ('name', )


class VideoShortlistResource(resources.ModelResource):

    class Meta:
        model = VideoShortlist
        import_id_fields = ('video_usage_key',)
        fields = ('video_usage_key', 'title')


@admin.register(VideoShortlist)
class VideoShortlistAdmin(ImportExportModelAdmin):
    """
    Django admin for VideoShortlist.
    """
    list_per_page = 800
    tmp_storage_class = CacheStorage
    resource_classes = [VideoShortlistResource]
    list_display = ('video_usage_key', 'is_processed',)
    search_fields = ('video_usage_key', 'is_processed',)
