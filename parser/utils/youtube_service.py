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


        android_data = await self._fetch_android_api(youtube_id)
        if android_data:
            return android_data

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

            Path("android_api_raw.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))

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

            if mime.startswith("video/") and "mp4" in mime:
                codecs = mime.lower()
                is_avc = "avc1" in codecs
                is_av1 = "av01" in codecs
                if not (is_avc or is_av1):
                    continue

                if not note:
                    continue
                note_clean = note.replace("p50", "p").replace("p60", "p")

                current = video_formats.get(note_clean)
                video_data = {
                    "file_size": int(size) if size else None,
                    "format_id": fid,
                    "url": fmt.get("url")  # 🔹 Добавлено
                }
                if not current:
                    video_formats[note_clean] = video_data
                else:
                    if is_avc and current.get("codec") != "avc1":
                        video_formats[note_clean] = video_data
                    elif current.get("codec") == ("avc1" if is_avc else "av01"):
                        if size and int(size) > int(current["file_size"] or 0):
                            video_formats[note_clean] = video_data

        def priority(fid):
            try:
                base_id = int(str(fid).split("-")[0])
            except ValueError:
                base_id = 0
            if base_id == 140:
                return 3
            elif base_id == 139:
                return 2
            return 1

        all_audio = []

        for fmt in formats:
            if not fmt.get("mimeType", "").startswith(AUDIO_MIME):
                continue

            lang_code = "unknown"
            display_name = "unknown"
            full_id = str(fmt.get("itag"))

            if "audioTrack" in fmt and fmt["audioTrack"].get("id"):
                lang_code = (fmt["audioTrack"].get("id", "").split(".")[0] or "unknown").lower()
                display_name = fmt["audioTrack"].get("displayName", "unknown")
            else:
                lang_code = "unknown"

            if lang_code not in LANG_WHITELIST:
                lang_code = "unknown"

            all_audio.append({
                "lang": lang_code,
                "display_name": display_name,
                "file_size": int(fmt.get("contentLength")) if fmt.get("contentLength") else None,
                "format_id": full_id,
                "format_note": fmt.get("audioQuality", ""),
                "is_default": fmt.get("audioTrack", {}).get("audioIsDefault", False),
                "url": fmt.get("url")  # 🔹 Добавлено
            })

        filtered = [a for a in all_audio if a["lang"] in ("ru", "en", "uz")]
        if not filtered:
            default_audio = [a for a in all_audio if a.get("is_default")]
            if default_audio:
                filtered = [max(default_audio, key=lambda x: priority(x["format_id"]))]
            elif all_audio:
                filtered = [max(all_audio, key=lambda x: priority(x["format_id"]))]
        else:
            best_per_lang = {}
            for a in filtered:
                lang = a["lang"]
                if lang not in best_per_lang:
                    best_per_lang[lang] = a
                else:
                    if priority(a["format_id"]) > priority(best_per_lang[lang]["format_id"]):
                        best_per_lang[lang] = a
                    elif priority(a["format_id"]) == priority(best_per_lang[lang]["format_id"]) and \
                            (a["file_size"] or 0) > (best_per_lang[lang]["file_size"] or 0):
                        best_per_lang[lang] = a
            filtered = list(best_per_lang.values())

        for a in filtered:
            audio_formats[a["lang"]] = {
                "file_size": a["file_size"],
                "format_id": a["format_id"],
                "format_note": a["format_note"],
                "display_name": a["display_name"],
                "url": a["url"]  # 🔹 Добавлено
            }

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
