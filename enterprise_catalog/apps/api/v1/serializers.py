from rest_framework import serializers

from enterprise_catalog.apps.catalog.models import (
    CatalogQuery,
    CatalogContentKey,
    EnterpriseCatalog
)


class QuerySerializerMixin:
    """
    Mixin for DRY query improvements

    Used by inheriting from the mixin and declaring the `related_fields` and `prefetch_fields` specific to the model
    on your serializer, and then calling `get_related_queries` when getting the queryset in your view.

    Adapted from https://riptutorial.com/django-rest-framework/example/7832/speed-up-serializers-queries
    """
    related_fields = []  # For selecting a single object (i.e. OneToOne or ForeignKey)
    prefetch_fields = []  # For selecting a group of objects (i.e. ManyToMany, reverse ForeignKeys, etc.)

    @classmethod
    def get_related_queries(cls, queryset):
        if cls.related_fields:
            queryset = queryset.select_related(*cls.related_fields)
        if cls.prefetch_fields:
            queryset = queryset.prefetch_related(*cls.prefetch_fields)

        return queryset


class CatalogQuerySerializer(QuerySerializerMixin, serializers.ModelSerializer):
    """
    Serializer for the `CatalogQuery` model
    """

    class Meta:
        model = CatalogQuery
        fields = ['id', 'title']

class CatalogContentKeySerializer(QuerySerializerMixin, serializers.ModelSerializer):
    """
    Serializer for the `CatalogContentKey` model
    """

    class Meta:
        model = CatalogContentKey
        fields = ['id']

class EnterpriseCatalogSerializer(QuerySerializerMixin, serializers.ModelSerializer):
    """
    Serializer for the `EnterpriseCatalogModel`
    """
    enterprise_customer = serializers.UUIDField(source='enterprise_uuid')

    class Meta:
        model = EnterpriseCatalog
        fields = ['uuid', 'title', 'enterprise_customer']


class EnterpriseCatalogDetailSerializer(EnterpriseCatalogSerializer):
    """
    Serializer for the `EnterpriseCatalog` model which includes
    the catalog's discovery service search query results.
    """

    def to_representation(self, instance):
        """
        Serialize the EnterpriseCatalog object.

        Arguments:
            instance (EnterpriseCatalog): The EnterpriseCatalog to serialize.

        Returns:
            dict: The EnterpriseCatalog converted to a dict.
        """

        catalog_query = instance.catalog_query

        representation = super(EnterpriseCatalogDetailSerializer, self).to_representation(instance)

        paginated_content = instance.get_paginated_content()
        previous_url = None
        next_url = None

        # request_uri = request.build_absolute_uri()
        # if paginated_content['previous']:
        #     previous_url = utils.update_query_parameters(request_uri, {'page': page - 1})
        # if paginated_content['next']:
        #     next_url = utils.update_query_parameters(request_uri, {'page': page + 1})

        representation['count'] = paginated_content['count']
        representation['results'] = paginated_content['results']
        representation['previous'] = previous_url
        representation['next'] = next_url

        return representation
