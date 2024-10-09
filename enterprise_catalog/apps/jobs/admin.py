"""
Admin for jobs models.
"""
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from enterprise_catalog.apps.jobs.models import Job, JobEnterprise, JobSkill


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """
    Django admin for Jobs.
    """
    list_display = ('job_id', 'external_id', 'title', 'description', )
    search_fields = ('job_id', 'title', 'description', )


@admin.register(JobEnterprise)
class JobEnterpriseAdmin(SimpleHistoryAdmin):
    """
    Django admin for Enterprise Jobs.
    """
    list_display = ('enterprise_uuid', 'created', 'modified', )
    search_fields = ('enterprise_uuid', )


@admin.register(JobSkill)
class JobSkillAdmin(SimpleHistoryAdmin):
    """
    Django admin for Job Skills.
    """
    list_display = ('skill_id', 'name', 'significance', 'created', 'modified',)
    search_fields = ('name', )
