from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from edx_rbac.admin import UserRoleAssignmentAdmin

from enterprise_catalog.apps.catalog.constants import (
    admin_model_changes_allowed,
)
from enterprise_catalog.apps.catalog.forms import (
    CatalogQueryForm,
    EnterpriseCatalogRoleAssignmentAdminForm,
)
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    ContentMetadata,
    EnterpriseCatalog,
    EnterpriseCatalogRoleAssignment,
)


class UnchangeableMixin(admin.ModelAdmin):
    """
    Mixin for disabling changing models through the admin

    We're disabling changing models in this admin while we transition over from the LMS
    """
    @classmethod
    def has_add_permission(cls, request):
        return admin_model_changes_allowed()

    @classmethod
    def has_delete_permission(cls, request, obj=None):
        return admin_model_changes_allowed()

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        if not admin_model_changes_allowed():
            extra_context['show_save_and_continue'] = False
            extra_context['show_save'] = False

        return super().changeform_view(request, object_id, extra_context=extra_context)


@admin.register(ContentMetadata)
class ContentMetadataAdmin(UnchangeableMixin):
    """ Admin configuration for the custom ContentMetadata model. """
    list_display = ('id', 'content_key', 'content_type',)


@admin.register(CatalogQuery)
class CatalogQueryAdmin(UnchangeableMixin):
    """ Admin configuration for the custom CatalogQuery model. """
    list_display = ('id',)
    form = CatalogQueryForm


@admin.register(EnterpriseCatalog)
class EnterpriseCatalogAdmin(UnchangeableMixin):
    """ Admin configuration for the custom EnterpriseCatalog model. """
    list_display = ('uuid', 'enterprise_uuid', 'enterprise_name', 'title', 'get_catalog_query',)

    def get_catalog_query(self, obj):
        link = reverse("admin:catalog_catalogquery_change", args=[obj.catalog_query.id])
        return format_html('<a href="{}">{}</a>', link, obj.catalog_query.content_filter_hash)

    get_catalog_query.short_description = 'Catalog Query'


@admin.register(EnterpriseCatalogRoleAssignment)
class EnterpriseCatalogRoleAssignmentAdmin(UserRoleAssignmentAdmin):
    """
    Django admin for EnterpriseCatalogRoleAssignment Model.
    """
    list_display = ('get_username', 'role', 'enterprise_id',)

    def get_username(self, obj):
        return obj.user.username

    class Meta:
        """
        Meta class for EnterpriseCatalogRoleAssignmentAdmin.
        """

        model = EnterpriseCatalogRoleAssignment

    fields = ('user', 'role', 'enterprise_id')
    form = EnterpriseCatalogRoleAssignmentAdminForm

    get_username.short_description = 'User'
