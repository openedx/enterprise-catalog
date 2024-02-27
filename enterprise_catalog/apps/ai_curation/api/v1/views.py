"""
REST API for AI Curation.
"""
import json
from uuid import UUID

from django_celery_results.models import TaskResult
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from enterprise_catalog.apps.ai_curation.api.serializers import (
    AICurationSerializer,
)
from enterprise_catalog.apps.ai_curation.api.throttle import (
    GetAICurationThrottle,
    PostAICurationThrottle,
)
from enterprise_catalog.apps.ai_curation.enums import AICurationStatus
from enterprise_catalog.apps.ai_curation.tasks import trigger_ai_curations


class AICurationView(APIView):
    """
    View for AI Curation.
    """
    authentication_classes = []
    permission_classes = []
    throttle_classes = [GetAICurationThrottle, PostAICurationThrottle]

    def get(self, request):
        """
        Return details (status and response) of the given task.
        """
        task_id = request.GET.get('task_id', None)
        if not task_id:
            return Response({'error': 'task_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            curation_task = TaskResult.objects.get(task_id=UUID(task_id))
            return Response({
                'status': curation_task.status,
                'result': json.loads(curation_task.result or '{}'),
            })
        except TaskResult.DoesNotExist:
            return Response({'error': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError:
            return Response({'error': 'Invalid task_id.'}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        """
        Trigger the AI curation process.

        This will first validate the payload, the following fields are required:
            1. query (str): User query that was input in the search bar.
            2. catalog_id (uuid): The catalog id for which the AI curation is being triggered.

        If the payload is valid, it will trigger the `trigger_ai_curations` celery task and return the task_id.
        """
        serializer = AICurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = trigger_ai_curations.delay(**serializer.validated_data)
        return Response({'task_id': str(task.task_id), 'status': AICurationStatus.PENDING})
