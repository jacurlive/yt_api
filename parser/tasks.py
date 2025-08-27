from celery import shared_task
from .utils.youtube_service import YouTubeInfoService
from .models import YouTubeVideo
import asyncio


@shared_task
def fetch_youtube_info_task(url):
    service = YouTubeInfoService(proxy="socks5://127.0.0.1:1080")

    info = asyncio.run(service.get_video_info(url))

    if not info or not info.get("ok") or "result" not in info:
        return {"ok": False, "result": None}

    data = info["result"]

    if not data.get("video_formats"):
        return {"ok": False, "result": None}

    video, created = YouTubeVideo.objects.get_or_create(
        youtube_key=data["youtube_key"],
        defaults={
            "title": data["title"],
            "duration": data["duration"],
            "author": data["author"],
            "upload_date": data["upload_date"],
            "video_formats": data["video_formats"],
            "audio_formats": data["audio_formats"],
        }
    )

    data["status"] = "created" if created else "already_exists"

    return {"ok": True, "result": data}
