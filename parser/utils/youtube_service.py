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
        print(f"[DEBUG] Обрабатываем видео: {youtube_id}")

        print("[DEBUG] Загружаем видео-данные из Android API...")
        android_data = await self._fetch_android_api(youtube_id)
        video_formats = {}
        meta_from_android = {}
        if android_data and android_data.get("status") == "success":
            video_formats = android_data["data"].get("video_formats", {})
            meta_from_android = {
                "youtube_key": android_data["data"].get("youtube_key"),
                "title": android_data["data"].get("title"),
                "duration": android_data["data"].get("duration"),
                "author": android_data["data"].get("author"),
                "upload_date": android_data["data"].get("upload_date"),
                "thumbnail": android_data["data"].get("thumbnail"),
            }
        print(f"[DEBUG] Видео форматов от Android API: {len(video_formats)}")

        print("[DEBUG] Загружаем аудио-данные из yt-dlp...")
        ytdlp_audio = self._fetch_ytdlp_audio_only(url)
        audio_formats = ytdlp_audio.get("audio_formats", {}) if ytdlp_audio else {}
        meta_from_ytdlp = ytdlp_audio.get("meta", {}) if ytdlp_audio else {}
        print(f"[DEBUG] Аудио форматов от yt-dlp: {len(audio_formats)}")

        meta = {
            "youtube_key": meta_from_android.get("youtube_key") or meta_from_ytdlp.get("youtube_key"),
            "title": meta_from_android.get("title") or meta_from_ytdlp.get("title"),
            "duration": meta_from_android.get("duration") or meta_from_ytdlp.get("duration"),
            "author": meta_from_android.get("author") or meta_from_ytdlp.get("author"),
            "upload_date": meta_from_android.get("upload_date") or meta_from_ytdlp.get("upload_date"),
            "thumbnail": meta_from_android.get("thumbnail") or meta_from_ytdlp.get("thumbnail"),
        }

        status_value = "success" if (video_formats or audio_formats) else "fail"
        result = {
            "status": status_value,
            "data": {
                **meta,
                "video_formats": video_formats,
                "audio_formats": audio_formats,
            }
        }
        print(f"[DEBUG] Итоговый статус: {result['status']}")
        return result

    def _fetch_ytdlp_audio_only(self, url: str):
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                raw_info = ydl.extract_info(url, download=False)

            youtube_key = raw_info.get('id')
            title = raw_info.get('title')
            duration = raw_info.get('duration')
            author = raw_info.get('channel') or raw_info.get('uploader')
            upload_date = None
            if raw_info.get('upload_date'):
                try:
                    upload_date = datetime.strptime(raw_info['upload_date'], "%Y%m%d").date()
                except Exception:
                    upload_date = None
            thumbnail = f'https://i.ytimg.com/vi/{youtube_key}/maxresdefault.jpg' if youtube_key else None
            all_formats = raw_info.get('formats') or []

            audio_formats = self._parse_audio_formats_enhanced(all_formats)
            return {
                "audio_formats": audio_formats,
                "meta": {
                    "youtube_key": youtube_key,
                    "title": title,
                    "duration": duration,
                    "author": author,
                    "upload_date": str(upload_date) if upload_date else None,
                    "thumbnail": thumbnail,
                }
            }
        except Exception as e:
            print(f"[yt-dlp audio-only error] {e}")
            return None

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

    def _parse_video_formats_enhanced(self, formats):
        video_formats = {}

        print(f"[DEBUG] Всего видео форматов: {len([f for f in formats if f.get('vcodec') != 'none' and (f.get('ext') == VIDEO_EXT or f.get('video_ext') == VIDEO_EXT)])}")

        debug_skips = 0
        for fmt in formats:
            if fmt.get("vcodec") == "none":
                continue
            if not (fmt.get("ext") == VIDEO_EXT or fmt.get("video_ext") == VIDEO_EXT):
                if debug_skips < 10:
                    print(f"[DEBUG] SKIP video (container): id={fmt.get('format_id')} ext={fmt.get('ext')} video_ext={fmt.get('video_ext')} vcodec={fmt.get('vcodec')} proto={fmt.get('protocol')}")
                    debug_skips += 1
                continue
            
            if fmt.get("protocol") == "m3u8_native":
                if debug_skips < 10:
                    print(f"[DEBUG] SKIP video (m3u8): id={fmt.get('format_id')}")
                    debug_skips += 1
                continue

            note = fmt.get("format_note")
            height = fmt.get("height")

            if note:
                note_clean = note.replace("p50", "p").replace("p60", "p")
            elif height:
                note_clean = f"{int(height)}p"
            else:
                if debug_skips < 10:
                    print(f"[DEBUG] SKIP video (no quality): id={fmt.get('format_id')} note={note} height={height}")
                    debug_skips += 1
                continue
            
            size = fmt.get("filesize") or fmt.get("filesize_approx")

            codec = (fmt.get("vcodec") or "").lower()
            is_avc = "avc1" in codec or "h264" in codec
            is_av1 = "av01" in codec
            
            if not (is_avc or is_av1):
                if debug_skips < 10:
                    print(f"[DEBUG] SKIP video (codec): id={fmt.get('format_id')} vcodec={codec}")
                    debug_skips += 1
                continue

            print(f"[DEBUG] Видео формат: {note_clean}, кодек: {codec}, размер: {size}")

            current = video_formats.get(note_clean)
            video_data = {
                "file_size": int(size) if size else None,
                "format_id": fmt.get("format_id"),
                "codec": "avc1" if is_avc else "av01",
            }

            if not current:
                video_formats[note_clean] = video_data
                print(f"[DEBUG] Добавлен новый формат: {note_clean}")
            else:

                if is_avc and current.get("codec") != "avc1":
                    video_formats[note_clean] = video_data
                    print(f"[DEBUG] Заменен на AVC: {note_clean}")
                elif current.get("codec") == ("avc1" if is_avc else "av01"):

                    if size and int(size) > int(current["file_size"] or 0):
                        video_formats[note_clean] = video_data
                        print(f"[DEBUG] Заменен по размеру: {note_clean}")

        if not video_formats:
            sample = [
                {k: fmt.get(k) for k in ("format_id", "ext", "video_ext", "vcodec", "acodec", "height", "fps", "protocol", "format_note")}
                for fmt in formats[:8]
            ]
            print(f"[DEBUG] Видео форматы не выбраны. Пример форматов: {sample}")

        print(f"[DEBUG] Итоговые видео форматы: {list(video_formats.keys())}")
        return video_formats

    def _parse_audio_formats_enhanced(self, formats):
        audio_formats = {}
        all_audio = []

        total_audio_candidates = [
            f for f in formats
            if f.get('vcodec') == 'none' and (f.get('ext') in ('m4a', 'mp4') or f.get('audio_ext') == 'm4a')
        ]
        print(f"[DEBUG] Всего аудио форматов: {len(total_audio_candidates)}")

        for fmt in total_audio_candidates:
            raw_lang = (fmt.get("language") or "unknown").lower()
            if raw_lang.startswith("en"):
                lang_code = "en"
            elif raw_lang.startswith("ru"):
                lang_code = "ru"
            elif raw_lang.startswith("uz"):
                lang_code = "uz"
            else:
                lang_code = "unknown"

            display_name = fmt.get("language") or "unknown"
            full_id = str(fmt.get("format_id", ""))

            print(f"[DEBUG] Аудио формат: lang_raw={raw_lang}, lang={lang_code}, id={full_id}, note={fmt.get('format_note')}")

            if "-drc" in full_id:
                print(f"[DEBUG] Пропускаем DRC формат: {full_id}")
                continue

            size = fmt.get("filesize") or fmt.get("filesize_approx")
            
            all_audio.append({
                "lang": lang_code,
                "display_name": display_name,
                "file_size": int(size) if size else None,
                "format_id": full_id,
                "format_note": fmt.get("format_note", ""),
                "is_default": False,
            })

        print(f"[DEBUG] Собрано аудио форматов: {len(all_audio)}")
        for a in all_audio:
            print(f"[DEBUG] - {a['lang']}: {a['format_id']} ({a['display_name']})")

        filtered = [a for a in all_audio if a["lang"] in ("ru", "en", "uz")]
        
        print(f"[DEBUG] Отфильтровано по предпочтительным языкам: {len(filtered)}")
        
        if not filtered:
            if all_audio:
                filtered = [max(all_audio, key=lambda x: self._priority(x["format_id"]))]
                print(f"[DEBUG] Выбран лучший доступный: {filtered[0]['lang']}")
        else:
            best_per_lang = {}
            for a in filtered:
                lang = a["lang"]
                if lang not in best_per_lang:
                    best_per_lang[lang] = a
                    print(f"[DEBUG] Первый формат для {lang}: {a['format_id']}")
                else:
                    current_priority = self._priority(best_per_lang[lang]["format_id"])
                    new_priority = self._priority(a["format_id"])
                    
                    if new_priority > current_priority:
                        best_per_lang[lang] = a
                        print(f"[DEBUG] Заменен {lang}: {a['format_id']} (приоритет {new_priority} > {current_priority})")
                    elif new_priority == current_priority and (a["file_size"] or 0) > (best_per_lang[lang]["file_size"] or 0):
                        best_per_lang[lang] = a
                        print(f"[DEBUG] Заменен {lang} по размеру: {a['format_id']} ({a['file_size']} > {best_per_lang[lang]['file_size']})")
            
            filtered = list(best_per_lang.values())
            print(f"[DEBUG] Итоговые лучшие форматы: {[a['lang'] + ':' + a['format_id'] for a in filtered]}")

        for a in filtered:
            audio_formats[a["lang"]] = {
                "file_size": a["file_size"],
                "format_id": a["format_id"],
                "format_note": a["format_note"],
                "display_name": a["display_name"],
            }

        return audio_formats

    def _priority(self, fid):
        try:
            base_id = int(str(fid).split("-")[0])
        except ValueError:
            base_id = 0
        if base_id == 140:
            return 3
        elif base_id == 139:
            return 2
        return 1

    def _extract_id(self, url: str) -> str:
        if "v=" in url:
            return url.split("v=")[1].split("&")[0]
        return url.split("/")[-1]
