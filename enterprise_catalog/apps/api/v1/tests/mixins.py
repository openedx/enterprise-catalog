from enterprise_catalog.apps.api.v1 import serializers


class SerializationMixin:
    """
    Mixin for more convenient serialization of objects for API tests
    """
    def _serialize_object(self, serializer, obj, many=False):
        return serializer(obj, many=many).data

    def serialize_enterprise_catalog(self, enterprise_catalog, many=False):
        return self._serialize_object(serializers.EnterpriseCatalogSerializer, enterprise_catalog, many)
