"""
REST API for AI Curation.
"""
import json
from uuid import UUID

from celery.states import SUCCESS
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
from enterprise_catalog.apps.ai_curation.errors import AICurationError
from enterprise_catalog.apps.ai_curation.tasks import trigger_ai_curations
from enterprise_catalog.apps.ai_curation.utils import get_tweaked_results


class AICurationView(APIView):
    """
    View for AI Curation.
    """
    authentication_classes = []
    permission_classes = []
    throttle_classes = [GetAICurationThrottle, PostAICurationThrottle]

    @staticmethod
    def _get_tweaked_curation_result(task_id, threshold):
        """
        Get the curation task result with the threshold applied.
        """
        try:
            return Response({
                'status': SUCCESS,
                'result': get_tweaked_results(task_id, float(threshold)),
            })
        except ValueError:
            return Response({'error': 'Invalid threshold.'}, status=status.HTTP_400_BAD_REQUEST)
        except AICurationError as error:
            return Response({'error': error.message}, status=error.status_code)

    def get(self, request):
        """
        Return details (status and response) of the given task.
        """
        task_id = request.GET.get('task_id', None)
        threshold = request.GET.get('threshold', None)
        if not task_id:
            return Response({'error': 'task_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            task_id = UUID(task_id)
        except ValueError:
            return Response({'error': 'Invalid task_id.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate that the task is complete.
        try:
            curation_task = TaskResult.objects.get(task_id=task_id)
        except TaskResult.DoesNotExist:
            return Response({'error': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)

        # User is trying to tweak results, make sure task has been completed. Otherwise, return 425.
        if threshold:
            if curation_task.status == SUCCESS:
                return self._get_tweaked_curation_result(task_id, threshold)
            else:
                return Response(
                    {'error': 'Evaluation of curations is not complete yet.'}, status=status.HTTP_425_TOO_EARLY
                )

        # If threshold is not provided, return the original curation result.
        # result will be empty dict if the task is not complete.
        return Response({
            'status': curation_task.status,
            'result': json.loads(curation_task.result or '{}'),
        })

    def post(self, request):
        """
        Trigger the AI curation process.

        This will first validate the payload, the following fields are required:
            1. query (str): User query that was input in the search bar.
            2. catalog_name (str): The catalog name for which the AI curation is being triggered.

        If the payload is valid, it will trigger the `trigger_ai_curations` celery task and return the task_id.
        """
        serializer = AICurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # 9 is the highest priority for the task
        # Find more information at https://docs.celeryq.dev/en/stable/userguide/routing.html#redis-message-priorities
        task = trigger_ai_curations.apply_async(kwargs=serializer.validated_data, priority=9)
        return Response({'task_id': str(task.task_id), 'status': task.status})
