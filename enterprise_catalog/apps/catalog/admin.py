from config_models.admin import ConfigurationModelAdmin
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
    CatalogUpdateCommandConfig,
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
    def has_add_permission(cls, request):  # pylint: disable=arguments-differ
        return admin_model_changes_allowed()

    @classmethod
    def has_delete_permission(cls, request, obj=None):  # pylint: disable=arguments-differ
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
    list_display = (
        'id',  # added to facilitate creating highlighted content (curation app) via the ContentMetadata `id`.
        'content_key',
        'content_type',
        'parent_content_key',
    )
    list_filter = (
        'content_type',
    )
    search_fields = (
        'content_key',
        'parent_content_key',
    )
    readonly_fields = (
        'associated_content_metadata',
        'catalog_queries',
        'get_catalog',
        'modified',
    )

    @admin.display(description='Enterprise Catalogs')
    def get_catalog(self, obj):
        catalogs = EnterpriseCatalog.objects.filter(
            catalog_query_id__in=obj.catalog_queries.all().values_list('id')
        )
        return f"{list(catalogs)}"


@admin.register(CatalogQuery)
class CatalogQueryAdmin(UnchangeableMixin):
    """ Admin configuration for the custom CatalogQuery model. """
    fields = (
        'uuid',
        'title',
        'content_filter',
    )
    readonly_fields = ('uuid',)
    list_display = (
        'uuid',
        'content_filter_hash',
        'get_content_filter',
    )
    search_fields = (
        'content_filter_hash',
    )

    @admin.display(
        description='Content Filter'
    )
    def get_content_filter(self, obj):
        return obj.pretty_print_content_filter()
    form = CatalogQueryForm


@admin.register(EnterpriseCatalog)
class EnterpriseCatalogAdmin(UnchangeableMixin):
    """ Admin configuration for the custom EnterpriseCatalog model. """
    list_display = (
        'uuid',
        'enterprise_uuid',
        'enterprise_name',
        'title',
        'get_catalog_query',
    )

    search_fields = (
        'uuid',
        'enterprise_uuid',
        'enterprise_name',
        'title',
        'catalog_query__content_filter_hash__exact'
    )

    @admin.display(
        description='Catalog Query'
    )
    def get_catalog_query(self, obj):
        link = reverse("admin:catalog_catalogquery_change", args=[obj.catalog_query.id])
        return format_html('<a href="{}">{}</a>', link, obj.catalog_query.pretty_print_content_filter())


@admin.register(EnterpriseCatalogRoleAssignment)
class EnterpriseCatalogRoleAssignmentAdmin(UserRoleAssignmentAdmin):
    """
    Django admin for EnterpriseCatalogRoleAssignment Model.
    """
    list_display = (
        'get_username',
        'role',
        'enterprise_id',
    )

    @admin.display(
        description='User'
    )
    def get_username(self, obj):
        return obj.user.username

    class Meta:
        """
        Meta class for EnterpriseCatalogRoleAssignmentAdmin.
        """

        model = EnterpriseCatalogRoleAssignment

    fields = ('user', 'role', 'enterprise_id', 'applies_to_all_contexts')
    form = EnterpriseCatalogRoleAssignmentAdminForm


admin.site.register(CatalogUpdateCommandConfig, ConfigurationModelAdmin)
