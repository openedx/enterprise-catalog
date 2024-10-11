from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
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
    RestrictedCourseMetadata,
    RestrictedRunAllowedForRestrictedCourse,
)


def _html_list_from_objects(objs, viewname, str_callback=str):
    """
    Get a pretty, clickable list of objects.

    Args:
      objs (iterable of Django ORM objects): List/queryset of objects to display.
      viewname (str): The `viewname` representing the django admin "change" view for the objects in obj.
      str_callback (callable): Optionally, a function to stringify one object for display purposes.
    """
    return format_html_join(
        # I already tried proper HTML lists, but they format really weird in django admin.
        sep=mark_safe('<br>'),
        format_string='<a href="{}">{}</a>',
        args_generator=((reverse(viewname, args=[obj.pk]), str_callback(obj)) for obj in objs),
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
        'get_catalog_queries',
        'get_catalogs',
        'get_restricted_courses_for_this_course',
        'get_restricted_courses_for_this_restricted_run',
        'modified',
    )
    exclude = (
        'catalog_queries',
    )

    @admin.display(description='Catalog Queries')
    def get_catalog_queries(self, obj):
        catalog_queries = obj.catalog_queries.all()
        return _html_list_from_objects(
            objs=catalog_queries,
            viewname="admin:catalog_catalogquery_change",
            str_callback=lambda cq: cq.short_str_for_listings(),
        )

    @admin.display(description='Enterprise Catalogs')
    def get_catalogs(self, obj):
        catalogs = EnterpriseCatalog.objects.filter(
            catalog_query_id__in=obj.catalog_queries.all().values_list('id')
        )
        return _html_list_from_objects(catalogs, "admin:catalog_enterprisecatalog_change")

    @admin.display(description='Restricted Courses For This Course')
    def get_restricted_courses_for_this_course(self, obj):
        restricted_courses = RestrictedCourseMetadata.objects.filter(unrestricted_parent=obj)
        return _html_list_from_objects(restricted_courses, "admin:catalog_restrictedcoursemetadata_change")

    @admin.display(description='Restricted Courses For This Restricted Run')
    def get_restricted_courses_for_this_restricted_run(self, obj):
        restricted_runs_allowed_for_restricted_course = RestrictedRunAllowedForRestrictedCourse.objects.select_related(
            'course',
        ).filter(
            run=obj,
        )
        restricted_courses = (relationship.course for relationship in restricted_runs_allowed_for_restricted_course)
        return _html_list_from_objects(restricted_courses, "admin:catalog_restrictedcoursemetadata_change")

    def get_form(self, *args, **kwargs):
        addl_help_texts = {
            'get_restricted_courses_for_this_course': (
                'If this is a course, list any "restricted" versions of this course.'
            ),
            'get_restricted_courses_for_this_restricted_run': (
                'If this is a restricted run, list all RestrictedCourses to which it is related.'
            ),
        }
        return super().get_form(*args, **(kwargs | {'help_texts': addl_help_texts}))


@admin.register(RestrictedCourseMetadata)
class RestrictedCourseMetadataAdmin(UnchangeableMixin):
    """ Admin configuration for the custom RestrictedCourseMetadata model. """
    list_display = (
        'content_key',
        'get_catalog_query_for_list',
        'get_unrestricted_parent',
    )
    search_fields = (
        'content_key',
        'catalog_query',
    )
    readonly_fields = (
        'get_catalog_query',
        'get_catalogs',
        'get_restricted_runs_allowed',
        'modified',
    )
    exclude = (
        'catalog_query',
    )

    @admin.display(
        description='Catalog Query'
    )
    def get_catalog_query_for_list(self, obj):
        link = reverse("admin:catalog_catalogquery_change", args=[obj.catalog_query.id])
        return format_html('<a href="{}">{}</a>', link, obj.catalog_query.short_str_for_listings())

    @admin.display(
        description='Catalog Query'
    )
    def get_catalog_query(self, obj):
        link = reverse("admin:catalog_catalogquery_change", args=[obj.catalog_query.id])
        return format_html('<a href="{}">{}</a>', link, obj.catalog_query.pretty_print_content_filter())

    @admin.display(
        description='Unrestricted Parent'
    )
    def get_unrestricted_parent(self, obj):
        link = reverse("admin:catalog_contentmetadata_change", args=[obj.unrestricted_parent.id])
        return format_html('<a href="{}">{}</a>', link, str(obj.unrestricted_parent))

    @admin.display(description='Enterprise Catalogs')
    def get_catalogs(self, obj):
        catalogs = EnterpriseCatalog.objects.filter(catalog_query=obj.catalog_query)
        return _html_list_from_objects(catalogs, "admin:catalog_enterprisecatalog_change")

    @admin.display(description='Restricted Runs Allowed')
    def get_restricted_runs_allowed(self, obj):
        restricted_runs_allowed_for_restricted_course = RestrictedRunAllowedForRestrictedCourse.objects.select_related(
            'run',
        ).filter(
            course=obj,
        )
        restricted_runs = (relationship.run for relationship in restricted_runs_allowed_for_restricted_course)
        return _html_list_from_objects(restricted_runs, "admin:catalog_contentmetadata_change")


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

    autocomplete_fields = (
        'catalog_query',
    )

    list_select_related = (
        'catalog_query',
    )

    readonly_fields = ('get_content_metadata_count',)

    @admin.display(
        description='Number of content records associated with the catalog'
    )
    def get_content_metadata_count(self, obj):
        return len(obj.catalog_query.contentmetadata_set.all())

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
