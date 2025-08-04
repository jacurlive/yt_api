import yt_dlp
from datetime import datetime

VIDEO_EXT = 'mp4'
AUDIO_EXT = 'm4a'
LEGACY_FORMATS = ["17", "18", "22"]
ALLOWED_QUALITIES = ['144p', '240p', '360p', '480p', '720p', '1080p', '1440p', '2160p']


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

        print("\n✅ FULL FORMAT LIST:\n")
        for fmt in all_formats:
            print(fmt)

        # Обработка видео
        video_formats = self._select_video_formats(all_formats)

        # Обработка аудио
        audio_formats = self._select_audio_formats(all_formats)

        return {
            "youtube_key": youtube_key,
            "title": title,
            "duration": duration,
            "author": author,
            "upload_date": upload_date,
            "thumbnail": thumbnail,
            "video_formats": video_formats,
            "audio_formats": audio_formats,
        }

    def _select_video_formats(self, all_formats: list) -> list:
        grouped = {}

        for fmt in all_formats:
            format_id = fmt.get("format_id")
            format_ext = fmt.get("ext")
            protocol = fmt.get("protocol")
            vcodec = fmt.get("vcodec")
            format_note = fmt.get("format_note")

            if (
                format_id in LEGACY_FORMATS
                or format_ext != VIDEO_EXT
                or protocol == "m3u8_native"
                or not vcodec or vcodec == "none"
                or not format_note
                or format_note not in ALLOWED_QUALITIES
            ):
                continue

            key = format_note
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(fmt)

        selected_formats = []
        for quality in ALLOWED_QUALITIES:
            candidates = grouped.get(quality, [])
            if not candidates:
                continue

            # avc приоритет, иначе берём первый
            avc = [f for f in candidates if 'avc' in (f.get('vcodec') or '')]
            best = sorted(avc, key=lambda x: int(x.get('format_id', 0)))[-1] if avc else sorted(candidates, key=lambda x: int(x.get('format_id', 0)))[-1]

            selected_formats.append({
                "format_id": best.get("format_id"),
                "format_note": best.get("format_note"),
                "file_size": best.get("filesize") or best.get("filesize_approx"),
                "width": best.get("width"),
                "height": best.get("height"),
                "ext": best.get("ext"),
                "protocol": best.get("protocol"),
                "vcodec": best.get("vcodec"),
            })

        return selected_formats

    def _select_audio_formats(self, all_formats: list) -> list:
        candidates = [
            f for f in all_formats
            if f.get("vcodec") == "none"
            and f.get("acodec") != "none"
            and f.get("ext") == AUDIO_EXT
            and f.get("protocol") != "m3u8_native"
        ]

        # Фильтрация: убрать DRC, если есть вариант без него
        filtered = {}
        for fmt in candidates:
            fid = fmt.get("format_id", "")
            base = fid.split("-")[0]

            if base not in filtered:
                filtered[base] = []

            filtered[base].append(fmt)

        result = []
        for group in filtered.values():
            # приоритет формата без "-drc"
            clean = [f for f in group if "-drc" not in f.get("format_id", "")]
            final = clean if clean else group
            for fmt in final:
                result.append({
                    "format_id": fmt.get("format_id"),
                    "abr": fmt.get("abr"),
                    "file_size": fmt.get("filesize") or fmt.get("filesize_approx"),
                    "language": fmt.get("language") or fmt.get("asr") or "unknown",
                    "ext": fmt.get("ext"),
                    "protocol": fmt.get("protocol")
                })

        return result

