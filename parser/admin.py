from django.contrib import admin
from .models import YouTubeVideo


@admin.register(YouTubeVideo)
class YouTubeVideAdmin(admin.ModelAdmin):
    list_display = ("youtube_key", "title", "created_at")
