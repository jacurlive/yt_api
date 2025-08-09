import yt_dlp
import aiohttp
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode

VIDEO_EXT = 'mp4'
AUDIO_MIME = 'audio/mp4'
LANG_WHITELIST = ["ru", "en", "uz", "unknown"]

PO_TOKEN = "MnRpTDYba2xwfml0w0uMytWe1C87DBsl8NAJI_hRlHJFW3oT3vHCFrikse7IxW0vco47ouqNa4D1IXuOYN5UQWeSEPO3Pz__soow3VbJvKsArLs4uhhZRR-XfwpPMa4-v28LsAEuoeg8TMfMk29vgtJPdedpgQ=="
VISITOR_DATA = "CgtYZmQ5MEoyQV9lRSjtvsy2BjIKCgJJThIEGgAgGw%3D%3D"

ANDROID_HEADERS = {
    "user-agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip"
}


class YouTubeInfoService:
    def __init__(self, proxy=None):
        self.proxy = proxy
        self.ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'proxy': proxy,
        }

    async def get_video_info(self, url: str) -> dict:
        youtube_id = self._extract_id(url)

        # 1 — Пробуем Android API
        android_data = await self._fetch_android_api(youtube_id)
        if android_data:
            return android_data

        # 2 — Если не удалось, пробуем через yt-dlp
        return self._fetch_yt_dlp(url)

    async def _fetch_android_api(self, youtube_id: str):
        base_url = "https://www.youtube.com/youtubei/v1/player"
        params = {
            "key": "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8",
            "contentCheckOk": True,
            "racyCheckOk": True,
            "videoId": youtube_id
        }

        payload = {
            "context": {
                "client": {
                    "clientName": "ANDROID",
                    "clientVersion": "19.09.37",
                    "androidSdkVersion": 30,
                    "userAgent": ANDROID_HEADERS["user-agent"],
                    "hl": "en",
                    "timeZone": "UTC",
                    "utcOffsetMinutes": 0,
                    "visitorData": VISITOR_DATA
                }
            },
            "playbackContext": {
                "contentPlaybackContext": {
                    "poToken": PO_TOKEN
                }
            }
        }

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(f"{base_url}?{urlencode(params)}",
                                        headers=ANDROID_HEADERS,
                                        json=payload,
                                        proxy=self.proxy,
                                        timeout=15) as res:
                    data = await res.json()

            # Path("android_api_raw.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))

            if "streamingData" not in data:
                return None

            return self._parse_android_response(data, youtube_id)

        except Exception as e:
            print(f"[Android API error] {e}")
            return None

    def _parse_android_response(self, data, youtube_id):
        video_formats = {}
        audio_formats = {}

        formats = data["streamingData"].get("adaptiveFormats", [])
        for fmt in formats:
            mime = fmt.get("mimeType", "")
            size = fmt.get("contentLength")
            fid = str(fmt.get("itag"))
            note = fmt.get("qualityLabel")

            # ==== Видео ====
            if mime.startswith("video/") and "mp4" in mime:
                codecs = mime.lower()
                # приоритет avc1, потом av01
                is_avc = "avc1" in codecs
                is_av1 = "av01" in codecs

                if not (is_avc or is_av1):
                    continue  # пропускаем всё остальное

                if not note:
                    continue
                note_clean = note.replace("p50", "p").replace("p60", "p")

                current = video_formats.get(note_clean)
                # Записываем приоритет: сначала avc1, потом av01
                if not current:
                    video_formats[note_clean] = {
                        "file_size": int(size) if size else None,
                        "format_id": fid,
                        # "codec": "avc1" if is_avc else "av01"
                    }
                else:
                    # Если оба с одинаковым разрешением, но один avc1 — заменяем
                    if is_avc and current.get("codec") != "avc1":
                        video_formats[note_clean] = {
                            "file_size": int(size) if size else None,
                            "format_id": fid,
                            # "codec": "avc1"
                        }
                    # Если кодек тот же, но размер больше — заменяем
                    elif current.get("codec") == ("avc1" if is_avc else "av01"):
                        if size and int(size) > int(current["file_size"] or 0):
                            video_formats[note_clean] = {
                                "file_size": int(size),
                                "format_id": fid,
                                # "codec": "avc1" if is_avc else "av01"
                            }

            elif mime.startswith(AUDIO_MIME):
                lang = fmt.get("language") or "unknown"
                lang = lang.lower()
                if lang not in LANG_WHITELIST:
                    lang = "unknown"

                fid = int(fmt.get("itag", 0))
                # приоритет: 140 -> 139 -> остальное m4a по убыванию itag
                if lang not in audio_formats:
                    audio_formats[lang] = {
                        "file_size": int(size) if size else None,
                        "format_id": str(fid),
                        "format_note": fmt.get("audioQuality", "")
                    }
                else:
                    current_fid = int(audio_formats[lang]["format_id"])
                    def priority(itag):
                        if itag == 140:
                            return 3
                        elif itag == 139:
                            return 2
                        return 1
                    if priority(fid) > priority(current_fid) or (
                        priority(fid) == priority(current_fid) and fid > current_fid
                    ):
                        audio_formats[lang] = {
                            "file_size": int(size) if size else None,
                            "format_id": str(fid),
                            "format_note": fmt.get("audioQuality", "")
                        }


        # дата
        upload_date = None
        try:
            if "uploadDate" in data["videoDetails"]:
                upload_date = datetime.strptime(data["videoDetails"]["uploadDate"], "%Y-%m-%d").date()
            else:
                upload_date = datetime.utcnow().date()
        except:
            upload_date = datetime.utcnow().date()

        return {
            "status": "success" if video_formats else "fail",
            "data": {
                "youtube_key": youtube_id,
                "title": data["videoDetails"]["title"],
                "duration": int(data["videoDetails"]["lengthSeconds"]),
                "author": data["videoDetails"]["author"],
                "upload_date": str(upload_date),
                "thumbnail": data["videoDetails"]["thumbnail"]["thumbnails"][-1]["url"],
                "video_formats": video_formats,
                "audio_formats": audio_formats
            }
        }

    def _fetch_yt_dlp(self, url):
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            raw_info = ydl.extract_info(url, download=False)

        youtube_key = raw_info['id']
        title = raw_info['title']
        duration = raw_info['duration']
        author = raw_info.get('channel') or raw_info.get('uploader')
        upload_date = datetime.strptime(raw_info['upload_date'], "%Y%m%d").date()
        thumbnail = f'https://i.ytimg.com/vi/{youtube_key}/maxresdefault.jpg'
        all_formats = raw_info['formats']

        video_formats = {}
        for fmt in all_formats:
            if fmt.get("ext") != VIDEO_EXT or fmt.get("protocol") == "m3u8_native":
                continue
            note = fmt.get("format_note")
            if not note:
                continue
            note_clean = note.replace("p50", "p").replace("p60", "p")
            size = fmt.get("filesize") or fmt.get("filesize_approx")
            current = video_formats.get(note_clean)
            if not current or (size and size > (current["file_size"] or 0)):
                video_formats[note_clean] = {
                    "file_size": size,
                    "format_id": fmt.get("format_id")
                }

        audio_formats = {}
        for fmt in all_formats:
            if fmt.get("vcodec") != "none" or fmt.get("ext") != "m4a":
                continue
            lang = (fmt.get("language") or "unknown").lower()
            if lang not in LANG_WHITELIST:
                lang = "unknown"
            fid = fmt.get("format_id", "")
            if "-drc" in fid and lang in audio_formats:
                continue
            size = fmt.get("filesize") or fmt.get("filesize_approx")
            audio_formats[lang] = {
                "file_size": size,
                "format_id": fid,
                "format_note": fmt.get("format_note", "")
            }

        return {
            "status": "success" if video_formats else "fail",
            "data": {
                "youtube_key": youtube_key,
                "title": title,
                "duration": duration,
                "author": author,
                "upload_date": str(upload_date),
                "thumbnail": thumbnail,
                "video_formats": video_formats,
                "audio_formats": audio_formats
            }
        }

    def _extract_id(self, url: str) -> str:
        if "v=" in url:
            return url.split("v=")[1].split("&")[0]
        return url.split("/")[-1]
