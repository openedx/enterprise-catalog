from django import forms
from django.contrib import admin
from djangoql.admin import DjangoQLSchema, DjangoQLSearchMixin
from simple_history.admin import SimpleHistoryAdmin

from enterprise_catalog.apps.curation import models


class EnterpriseCurationConfigQLSchema(DjangoQLSchema):
    """
    DjangoQL schema for EnterpriseCurationConfigAdmin, primarily for enabling suggestions for `title` fields.
    """

    suggest_options = {
        models.EnterpriseCurationConfig: ['title'],
    }


class EnterpriseCurationConfigAdmin(DjangoQLSearchMixin, SimpleHistoryAdmin):
    """
    Admin configuration for the EnterpriseCurationConfig model.
    """

    djangoql_schema = EnterpriseCurationConfigQLSchema
    # explicitly set the fields, only for the purpose of predictable ordering in the Admin UI.
    fields = (
        'title',
        'enterprise_uuid',
        'is_highlight_feature_active',
    )
    list_display = (
        'uuid',
        'enterprise_uuid',
        'title',
        'is_highlight_feature_active',
    )

    def get_readonly_fields(self, request, obj=None):
        """
        Force enterprise_uuid to readonly mode, if and only if the current request is to edit an existing object.

        Rationale: I can't think of a valid reason to edit the enterprise_uuid.  Perhaps if you wanted to conveniently
        transfer all highlight sets from one enterprise customer to another, but even then this change needs to be
        coordinated with several other database changes, best suited for a management command anyway.
        """
        if obj:
            return self.readonly_fields + tuple(['enterprise_uuid'])
        else:
            # None obj implies the current page is a create object page.  Since the enterprise_uuid is a required field,
            # we must prevent it from being set as readonly in this case.
            return self.readonly_fields


class HighlightSetQLSchema(DjangoQLSchema):
    """
    DjangoQL schema for EnterpriseCurationConfigAdmin, primarily for enabling suggestions for `title` fields.
    """

    suggest_options = {
        models.HighlightSet: ['title'],
        models.EnterpriseCurationConfig: ['title'],
    }


class HighlightSetAdmin(DjangoQLSearchMixin, SimpleHistoryAdmin):
    """
    Admin config for HighlightSet model.
    """

    djangoql_schema = HighlightSetQLSchema
    list_display = (
        'uuid',
        'title',
        'enterprise_curation',
        'is_published',
    )


class HighlightedContentModelForm(forms.ModelForm):
    """
    Custom admin model form for HighlightedContent.

    This primarily exists to customize the field type for `content_metdata`.  By default, ForeignKey fields become
    drop-down menus in django admin, but that presents both UX and performance problems due to the possibly large amount
    of ContentMetadata values in production.  Instead, we change that field to be a TextInput representing the object
    ID, and provide some instructions for the admin.
    """

    class Meta:
        model = models.HighlightedContent
        fields = ['catalog_highlight_set', 'content_metadata']
        labels = {
            'content_metadata': 'Content Metadata ID',
        }
        help_texts = {
            'content_metadata': (
                'ID of the Content Metadata object (different than the content key), which is discoverable via the '
                '<a href="/admin/catalog/contentmetadata/">Content Metadata admin page</a>.'
            ),
        }
        widgets = {
            'content_metadata': forms.TextInput(),
        }


class HighlightedContentAdmin(DjangoQLSearchMixin, SimpleHistoryAdmin):
    """
    Admin config for HighlightedContent model.
    """

    form = HighlightedContentModelForm
    list_display = (
        'uuid',
        'catalog_highlight_set',
        'content_metadata',
    )


admin.site.register(models.EnterpriseCurationConfig, EnterpriseCurationConfigAdmin)
admin.site.register(models.HighlightSet, HighlightSetAdmin)
admin.site.register(models.HighlightedContent, HighlightedContentAdmin)
