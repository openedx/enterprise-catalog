# -*- coding: utf-8 -*-
"""
Forms to be used in enterprise catalog Django admin.
"""
from django import forms
from django.core.exceptions import ValidationError
from edx_rbac.admin import UserRoleAssignmentAdminForm

from enterprise_catalog.apps.catalog.constants import CONTENT_FILTER_FIELD_TYPES
from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    EnterpriseCatalogRoleAssignment,
)
from enterprise_catalog.apps.catalog.utils import get_content_filter_hash


class CatalogQueryForm(forms.ModelForm):
    """
    Django admin form for CatalogQueryAdmin
    """

    class Meta:
        model = CatalogQuery
        fields = ('content_filter',)

    def validate_content_filter_fields(self, content_filter):
        for key in CONTENT_FILTER_FIELD_TYPES:
            if key in content_filter.keys():
                if not isinstance(content_filter[key], CONTENT_FILTER_FIELD_TYPES[key]['type']):
                    raise ValidationError(
                        "Content filter '%s' must be of type %s" % (key, CONTENT_FILTER_FIELD_TYPES[key]['type'])
                    )
                if CONTENT_FILTER_FIELD_TYPES[key]['type'] == list:
                    if not all(isinstance(x, str) for x in content_filter[key]):
                        raise ValidationError(
                            "Content filter '%s' must contain values of type %s" % (
                                key, CONTENT_FILTER_FIELD_TYPES[key]['subtype']
                            )
                        )

    def clean_content_filter(self):
        content_filter = self.cleaned_data['content_filter']
        self.validate_content_filter_fields(content_filter)

        content_filter_hash = get_content_filter_hash(content_filter)
        if CatalogQuery.objects.filter(content_filter_hash=content_filter_hash).exists():
            raise ValidationError('Catalog Query with this Content filter already exists.')
        return content_filter


class EnterpriseCatalogRoleAssignmentAdminForm(UserRoleAssignmentAdminForm):
    """
    Django admin form for EnterpriseCatalogRoleAssignmentAdmin.
    """

    class Meta:
        """
        Meta class for EnterpriseCatalogRoleAssignmentAdminForm.
        """
        model = EnterpriseCatalogRoleAssignment
        fields = "__all__"
