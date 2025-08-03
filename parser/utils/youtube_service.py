import yt_dlp
from datetime import datetime

VIDEO_EXT = 'mp4'
AUDIO_EXT = 'm4a'
LEGACY_FORMATS = ["17", "18", "22"]
AUDIO_FORMATS = ['139', '140', '139-0', '140-0']
ALLOWED_QUALITIES = ['144p', '240p', '360p', '480p', '720p', '1080p', '1440p', '2160p', 'MP3']


class YouTubeInfoService:
    def __init__(self):
        self.ydl_opts = {
            'proxy': 'socks5://127.0.0.1:1080',
            'quiet': True,
            'skip_download': True,
        }

    def get_video_info(self, url: str) -> dict:
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            raw_info = ydl.extract_info(url, download=False)

        youtube_key = raw_info['id']
        title = raw_info['title']
        duration = raw_info['duration']
        author = raw_info.get('channel') or raw_info.get('uploader')
        upload_date = datetime.strptime(raw_info['upload_date'], "%Y%m%d").date()
        thumbnail = f'https://i.ytimg.com/vi/{youtube_key}/maxresdefault.jpg'
        all_formats = raw_info['formats']

        # Видео форматы
        video_formats = []
        for fmt in all_formats:
            format_data = self._process_video_format(fmt)
            if format_data:
                video_formats.append(format_data)

        # Аудио форматы
        audio_formats = []
        for fmt in all_formats:
            if fmt.get("vcodec") == "none" and fmt.get("acodec") != "none":
                audio_formats.append({
                    "format_id": fmt.get("format_id"),
                    "ext": fmt.get("ext"),
                    "abr": fmt.get("abr"),
                    "file_size": fmt.get("filesize") or fmt.get("filesize_approx"),
                    "language": fmt.get("language") or fmt.get("asr") or "unknown"
                })

        return {
            "youtube_key": youtube_key,
            "title": title,
            "duration": duration,
            "author": author,
            "upload_date": upload_date,
            "thumbnail": thumbnail,
            "video_formats": video_formats,
            "audio_formats": audio_formats
        }

    def _process_video_format(self, fmt: dict) -> dict | None:
        format_id = fmt.get("format_id")
        format_ext = fmt.get("ext")
        protocol = fmt.get("protocol")
        vcodec = fmt.get("vcodec")

        # Пропускаем лишние форматы
        if (
            format_id in LEGACY_FORMATS
            or format_ext != VIDEO_EXT
            or protocol == "m3u8_native"
            or not vcodec
            or vcodec == "none"
        ):
            return None

        if 'avc' not in vcodec:
            return None

        format_note = fmt.get("format_note") or "unknown"
        if format_note not in ALLOWED_QUALITIES:
            format_note = "MP3"

        return {
            "format_id": format_id,
            "format_note": format_note,
            "file_size": fmt.get("filesize") or fmt.get("filesize_approx"),
            "width": fmt.get("width"),
            "height": fmt.get("height")
        }
