from edx_rest_framework_extensions.auth.jwt.authentication import (
    JwtAuthentication,
)
from rest_framework import permissions, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer
from rest_framework_xml.renderers import XMLRenderer

from enterprise_catalog.apps.api.v1.serializers import VideoSerializer
from enterprise_catalog.apps.video_catalog.models import Video


class VideoReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    """ Viewset for Read Only operations on Videos """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [JSONRenderer, XMLRenderer]
    serializer_class = VideoSerializer
    queryset = Video.objects.all()
    lookup_field = 'edx_video_id'
