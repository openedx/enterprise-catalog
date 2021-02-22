# cookbook/schema.py
import graphene
from graphene_django import DjangoObjectType

from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class EnterpriseCatalogType(DjangoObjectType):
    something_not_on_model = graphene.String(name='yolo', default_value='you only live once')
    class Meta:
        model = EnterpriseCatalog
        fields = (
            'uuid',
            'title',
            'enterprise_uuid',
            'enterprise_name',
            'enabled_course_modes',
            'publish_audit_enrollment_urls',
        )

    # def resolve_something_not_on_model(root, info):
    #     return 'WHYYYYYY Hello There'

    def resolve_title(root, info):
        return 'an overwritten title!'
