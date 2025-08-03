from django.urls import path
from .views import VideoInfoCreateView, VideoTaskStatusView

urlpatterns = [
    path('video/', VideoInfoCreateView.as_view(), name='video-create'),
    path('status/<str:task_id>/', VideoTaskStatusView.as_view(), name='video-status'),
]
