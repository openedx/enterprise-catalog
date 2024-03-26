from django.utils.functional import cached_property
from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.academy.models import Academy
from enterprise_catalog.apps.api.v1.serializers import AcademySerializer


class AcademiesReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    """ Viewset for Read Only operations on Academies """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [JSONRenderer, XMLRenderer]
    serializer_class = AcademySerializer
    lookup_field = 'uuid'

    @cached_property
    def request_action(self):
        return getattr(self, 'action', None)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        academy_uuid = str(self.kwargs['uuid']) if 'uuid' in self.kwargs else ''
        context.update({'academy_uuid': academy_uuid})
        return context

    def get_queryset(self):
        """
        Returns the queryset corresponding to all academies the requesting user has access to.
        """
        enterprise_customer = self.request.GET.get('enterprise_customer', False)
        all_academies = Academy.objects.all()
        if self.request_action == 'list':
            if enterprise_customer:
                user_accessible_academy_uuids = []
                for academy in all_academies:
                    academy_associated_catalogs = academy.enterprise_catalogs.all()
                    enterprise_associated_catalogs = academy_associated_catalogs.filter(
                        enterprise_uuid=enterprise_customer
                    )
                    if enterprise_associated_catalogs:
                        user_accessible_academy_uuids.append(academy.uuid)
                return all_academies.filter(uuid__in=user_accessible_academy_uuids)
            else:
                return Academy.objects.none()

        return Academy.objects.all()
