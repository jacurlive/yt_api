from celery import shared_task
from .utils.youtube_service import YouTubeInfoService
from .models import YouTubeVideo


@shared_task
def fetch_youtube_info_task(url):
    service = YouTubeInfoService()
    info = service.get_video_info(url)

    video, created = YouTubeVideo.objects.get_or_create(
        youtube_key=info["youtube_key"],
        defaults={
            "title": info["title"],
            "duration": info["duration"],
            "author": info["author"],
            "upload_date": info["upload_date"],
            "video_formats": info["video_formats"],
            "audio_formats": info["audio_formats"],
        }
    )

    return {
        "youtube_key": info["youtube_key"],
        "title": info["title"],
        "duration": info["duration"],
        "author": info["author"],
        "upload_date": str(info["upload_date"]),
        "video_formats": info["video_formats"],
        "audio_formats": info["audio_formats"],
        "status": "created" if created else "already_exists"
    }
