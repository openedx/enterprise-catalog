from rest_framework import viewsets

from enterprise_catalog.apps.api.v1.serializers import EnterpriseCatalogSerializer
from enterprise_catalog.apps.catalog.models import EnterpriseCatalog


class EnterpriseCatalogViewSet(viewsets.ModelViewSet):
    """ View for CRUD operations on Enterprise Catalogs """
    serializer_class = EnterpriseCatalogSerializer
    queryset = EnterpriseCatalog.objects.all()
