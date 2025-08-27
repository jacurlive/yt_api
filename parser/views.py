from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import VideoRequestSerializer
from .tasks import fetch_youtube_info_task

from celery.result import AsyncResult


class VideoInfoCreateView(APIView):
    def post(self, request):
        serializer = VideoRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        url = serializer.validated_data['url']

        task = fetch_youtube_info_task.delay(url)
        return Response({"task_id": task.id}, status=status.HTTP_202_ACCEPTED)


class VideoTaskStatusView(APIView):
    def get(self, request, task_id):
        result = AsyncResult(task_id)

        if result.state == 'PENDING':
            return Response({"status": "pending"}, status=202)
        elif result.state == 'STARTED':
            return Response({"status": "started"}, status=202)
        elif result.state == 'SUCCESS':
            return Response(result.result, status=200)
        elif result.state == 'FAILURE':
            return Response({"status": "failed", "error": str(result.result)}, status=500)
        else:
            return Response({"status": result.state.lower()}, status=202)
