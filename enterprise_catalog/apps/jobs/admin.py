"""
Admin for jobs models.
"""
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from enterprise_catalog.apps.jobs.models import EnterpriseCustomer, Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """
    Django admin for Jobs.
    """
    list_display = ('id', 'title', 'description', )
    search_fields = ('title', 'description', )


@admin.register(EnterpriseCustomer)
class EnterpriseCustomerAdmin(SimpleHistoryAdmin):
    """
    Django admin for Enterprise Customers.
    """
    list_display = ('uuid', 'name', 'slug', 'created', 'modified', )
    search_fields = ('uuid', 'name', 'slug', )
