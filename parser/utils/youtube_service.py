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

    async def get_video_info(self, url: str) -> dict:
        youtube_id = self._extract_id(url)

        if len(youtube_id) != 11:
            return {
                "ok": False,
                "result": None
            }
        
        print(f"[DEBUG] Обрабатываем видео: {youtube_id}")

        print("[DEBUG] Загружаем данные через Android API...")
        android_data = await self._fetch_android_api(youtube_id)
        
        if not android_data:
            print("[DEBUG] Android API не вернул данные")
            return {
                "ok": False,
                "result": None
            }

        result = {
            "ok": True,
            "result": {
                "youtube_key": youtube_id,
                "title": android_data["data"].get("title"),
                "duration": android_data["data"].get("duration"),
                "author": android_data["data"].get("author"),
                "upload_date": android_data["data"].get("upload_date"),
                "thumbnail": f"https://i.ytimg.com/vi/{youtube_id}/maxresdefault.jpg",
                "video_formats": android_data["data"].get("video_formats", {}),
                "audio_formats": android_data["data"].get("audio_formats", {})
            }
        }
        
        print(f"[DEBUG] Успешно обработано видео: {result['result']['title']}")
        return result

    async def _fetch_android_api(self, youtube_id: str):
        """Android API вызов для получения всех данных"""
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
        video_formats = []
        audio_formats = []

        formats = data["streamingData"].get("adaptiveFormats", [])
        print(f"[DEBUG] Получено {len(formats)} форматов из Android API")

        video_formats_dict = {}
        
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
                    print(f"[DEBUG] Пропускаем видео (кодек): {fid} - {codecs}")
                    continue

                if not note:
                    print(f"[DEBUG] Пропускаем видео (нет качества): {fid}")
                    continue
                note_clean = note.replace("p50", "p").replace("p60", "p")

                current = video_formats_dict.get(note_clean)
                video_data = {
                    "format_note": note_clean,
                    "format_id": fid,
                    "file_size": int(size) if size else None,
                }
                
                if not current:
                    video_formats_dict[note_clean] = video_data
                    print(f"[DEBUG] Добавлен видео формат: {note_clean} - {fid}")
                else:
                    if is_avc and current.get("codec") != "avc1":
                        video_formats_dict[note_clean] = video_data
                        print(f"[DEBUG] Заменен на AVC: {note_clean}")
                    elif current.get("codec") == ("avc1" if is_avc else "av01"):
                        if size and int(size) > int(current["file_size"] or 0):
                            video_formats_dict[note_clean] = video_data
                            print(f"[DEBUG] Заменен по размеру: {note_clean}")

        video_formats = list(video_formats_dict.values())
        print(f"[DEBUG] Найдено видео форматов: {len(video_formats)}")

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

            print(f"[DEBUG] Аудио формат {full_id}:")
            print(f"  - audioTrack: {fmt.get('audioTrack')}")
            print(f"  - displayName: {fmt.get('displayName')}")
            print(f"  - language: {fmt.get('language')}")

            if "audioTrack" in fmt and fmt["audioTrack"].get("id"):
                raw_lang = fmt["audioTrack"].get("id", "").split(".")[0] or "unknown"
                display_name = fmt["audioTrack"].get("displayName", "unknown")
                
                if raw_lang.startswith("en"):
                    lang_code = "en"
                elif raw_lang.startswith("ru"):
                    lang_code = "ru"
                elif raw_lang.startswith("uz"):
                    lang_code = "uz"
                else:
                    lang_code = raw_lang.lower()
                
                print(f"  - Определен по audioTrack.id: {raw_lang} -> {lang_code}")
            else:
                display_name = fmt.get("displayName", "unknown")
                if "English" in display_name or "US" in display_name:
                    lang_code = "en"
                    print(f"  - Определен по displayName (English): {lang_code}")
                elif "Russian" in display_name or "Русский" in display_name:
                    lang_code = "ru"
                    print(f"  - Определен по displayName (Russian): {lang_code}")
                elif "Uzbek" in display_name or "o'zbek" in display_name:
                    lang_code = "uz"
                    print(f"  - Определен по displayName (Uzbek): {lang_code}")
                else:
                    lang_code = "unknown"
                    print(f"  - Не определен по displayName: {lang_code}")

            if lang_code == "unknown":
                if "English" in display_name or "US" in display_name:
                    lang_code = "en"
                    print(f"  - Переопределен по displayName (English): {lang_code}")
                elif "Russian" in display_name or "Русский" in display_name:
                    lang_code = "ru"
                    print(f"  - Переопределен по displayName (Russian): {lang_code}")
                elif "Uzbek" in display_name or "o'zbek" in display_name:
                    lang_code = "uz"
                    print(f"  - Переопределен по displayName (Uzbek): {lang_code}")

            if lang_code == "unknown":
                audio_track = fmt.get("audioTrack")
                has_audio_track = audio_track is not None
                has_display_name = display_name and display_name != "unknown"
                
                print(f"  - Проверяем поля: audioTrack={has_audio_track}, displayName={has_display_name}")
                
                if not has_audio_track and not has_display_name:
                    lang_code = None
                    print(f"  - Язык не определен, возвращаем None")
                else:
                    lang_code = "unknown"
                    print(f"  - Есть данные, но язык не определен, возвращаем unknown")
            elif lang_code not in LANG_WHITELIST:
                lang_code = "unknown"

            print(f"  - Финальный lang_code: {lang_code}")
            print(f"  - Финальный display_name: {display_name}")

            all_audio.append({
                "lang": lang_code,
                "display_name": display_name,
                "file_size": int(fmt.get("contentLength")) if fmt.get("contentLength") else None,
                "format_id": full_id,
                "format_note": fmt.get("audioQuality", ""),
                "is_default": fmt.get("audioTrack", {}).get("audioIsDefault", False),
            })

        print(f"[DEBUG] Найдено аудио форматов: {len(all_audio)}")
        print(f"[DEBUG] Все найденные языки: {list(set([a['lang'] for a in all_audio]))}")
        for a in all_audio:
            print(f"[DEBUG] Аудио: {a['lang']} - {a['format_id']} ({a['display_name']})")

        print(f"[DEBUG] Ищем языки: ru, en, uz")
        
        filtered = [a for a in all_audio if a["lang"] in ("ru", "en", "uz")]
        print(f"[DEBUG] Отфильтровано по предпочтительным языкам: {len(filtered)}")
        for a in filtered:
            print(f"[DEBUG] Отфильтрованный: {a['lang']} - {a['format_id']} ({a['display_name']})")
        
        if not filtered:
            default_audio = [a for a in all_audio if a.get("is_default")]
            if default_audio:
                filtered = [max(default_audio, key=lambda x: priority(x["format_id"]))]
                print(f"[DEBUG] Выбран дефолтный аудио: {filtered[0]['lang']}")
            elif all_audio:
                filtered = [max(all_audio, key=lambda x: priority(x["format_id"]))]
                print(f"[DEBUG] Выбран лучший аудио: {filtered[0]['lang']}")
        else:
            best_per_lang = {}
            for a in filtered:
                lang = a["lang"]
                if lang not in best_per_lang:
                    best_per_lang[lang] = a
                    print(f"[DEBUG] Первый для {lang}: {a['format_id']}")
                else:
                    current_priority = priority(best_per_lang[lang]["format_id"])
                    new_priority = priority(a["format_id"])
                    if new_priority > current_priority:
                        best_per_lang[lang] = a
                        print(f"[DEBUG] Заменен {lang}: {a['format_id']} (приоритет {new_priority} > {current_priority})")
                    elif new_priority == current_priority and (a["file_size"] or 0) > (best_per_lang[lang]["file_size"] or 0):
                        best_per_lang[lang] = a
                        print(f"[DEBUG] Заменен {lang} по размеру: {a['format_id']}")
            filtered = list(best_per_lang.values())

        for a in filtered:
            audio_formats.append({
                "lang_name": a["display_name"],
                "file_size": a["file_size"],
                "lang_code": a["lang"]
            })

        print(f"[DEBUG] Итоговые аудио форматы: {[a['lang_code'] for a in audio_formats]}")

        try:
            if "uploadDate" in data["videoDetails"]:
                upload_date = datetime.strptime(data["videoDetails"]["uploadDate"], "%Y-%m-%d").date()
            else:
                upload_date = datetime.utcnow().date()
        except:
            upload_date = datetime.utcnow().date()

        final_status = "success" if (video_formats or audio_formats) else "fail"
        print(f"[DEBUG] Финальный статус: {final_status} (видео: {len(video_formats)}, аудио: {len(audio_formats)})")

        return {
            "status": final_status,
            "data": {
                "youtube_key": youtube_id,
                "title": data["videoDetails"]["title"],
                "duration": int(data["videoDetails"]["lengthSeconds"]),
                "author": data["videoDetails"]["author"],
                "upload_date": str(upload_date),
                "video_formats": video_formats,
                "audio_formats": audio_formats
            }
        }

    def _extract_id(self, url: str) -> str:
        if "v=" in url:
            return url.split("v=")[1].split("&")[0]
        return url.split("/")[-1]
