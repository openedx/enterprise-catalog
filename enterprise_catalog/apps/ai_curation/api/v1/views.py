"""
REST API for AI Curation.
"""
from django.core.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from enterprise_catalog.apps.ai_curation.api.serializers import (
    AICurationSerializer,
)
from enterprise_catalog.apps.ai_curation.api.throttle import AICurationThrottle
from enterprise_catalog.apps.ai_curation.enums import AICurationStatus
from enterprise_catalog.apps.ai_curation.models import AICurationTask
from enterprise_catalog.apps.ai_curation.tasks import trigger_ai_curations


class AICurationView(APIView):
    """
    View for AI Curation.
    """
    authentication_classes = []
    permission_classes = []
    throttle_classes = [AICurationThrottle]

    def get(self, request):
        """
        Return a list of all users.
        """
        task_id = request.GET.get('task_id', None)
        if not task_id:
            return Response({'error': 'task_id is required.'}, status=400)
        try:
            curation_task = AICurationTask.objects.get(task_id=task_id)
            return Response({
                'status': curation_task.status,
                'result': curation_task.result,
            })
        except AICurationTask.DoesNotExist:
            return Response({'error': 'Task not found.'}, status=404)
        except ValidationError:
            return Response({'error': 'Invalid task_id.'}, status=400)

    def post(self, request):
        """
        Trigger the AI curation process.
        """
        serializer = AICurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = trigger_ai_curations.delay(**serializer.validated_data)
        return Response({'task_id': str(task.task_id), 'status': AICurationStatus.PENDING})
