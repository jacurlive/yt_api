from django.db import models


class YouTubeVideo(models.Model):
    youtube_key = models.CharField(max_length=150, unique=True)
    title = models.CharField(max_length=400)
    duration = models.IntegerField()
    author = models.CharField(max_length=255)
    upload_date = models.DateField()
    video_formats = models.JSONField()
    audio_formats = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.youtube_key} - {self.title}"
