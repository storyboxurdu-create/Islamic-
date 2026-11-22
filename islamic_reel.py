import asyncio
import json
import os
import random
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
import edge_tts

HISTORY_FILE = Path("islamic_history.json")
OUTPUT_VIDEO = Path("final_islamic_short.mp4")
OUTPUT_META = Path("video_meta.json")
OUTPUT_THUMBNAIL = Path("thumbnail.jpg")

LOCAL_MUSIC_CANDIDATES = [
    Path("assets/moody_music.mp3"),
    Path("assets/background_music.mp3"),
    Path("moody_music.mp3"),
    Path("background_music.mp3"),
]

LOCAL_CLIP_DIRS = [
    Path("assets/clips"),
    Path("assets"),
]

FONT_SOURCES = [
    (
        "Noto Naskh Arabic",
        "https://github.com/google/fonts/raw/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf",
        "NotoNaskhArabic.ttf",
    ),
    (
        "Noto Nastaliq Urdu",
        "https://github.com/google/fonts/raw/main/ofl/notonastaliqurdu/NotoNastaliqUrdu%5Bwght%5D.ttf",
        "NotoNastaliqUrdu.ttf",
    ),
]

MOODY_MUSIC_SOURCES = [
    "https://archive.org/download/relaxing-ambient-piano-music/Relaxing%20Ambient%20Piano%20Music.mp3",
    "https://archive.org/download/DarkAmbientMusic/Dark%20Ambient%201.mp3",
    "https://archive.org/download/SadPianoInstrumental/Sad%20Piano%20Instrumental.mp3",
]

TOPIC_POOL = [
    "Dajjal ka fitna aur iman bachane ka sabaq",
    "Yajooj Majooj ka zikr aur aane wale waqt ki yaad-dihani",
    "Aakhri Zamana ki aham nishaniyan aur ghaflat se bachna",
    "Hadees ki roshni mein zindagi aur aakhirat ka sabaq",
    "Nabiyon ke sachay waqiat se sabr aur yaqeen ka sabaq",
    "Sahaba ke achhay aur sachay waqiat se sachai aur qurbaani ka sabaq",
]

HOOK_ANGLES = [
    "Open immediately with a sharp, gripping line that pulls the viewer in within 2 seconds.",
    "Open with a direct, thought-provoking question tied to the topic without any slow intro.",
    "Start right inside the core moment or turning point of the event/reminder.",
    "Start with a strong contrast between worldly distraction and real spiritual awareness.",
]


def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                ids = [str(x) for x in (data.get("used_ids") or [])]
                summaries = [str(x) for x in (data.get("recent_summaries") or [])]
                return {"used_ids": ids, "recent_summaries": summaries}
            if isinstance(data, list):
                return {"used_ids": [str(x) for x in data], "recent_summaries": []}
        except Exception:
            pass
    return {"used_ids": [], "recent_summaries": []}


def save_history(history: dict) -> None:
    payload = {
        "used_ids": (history.get("used_ids") or [])[-150:],
        "recent_summaries": (history.get("recent_summaries") or [])[-15:],
    }
    HISTORY_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_json_object(raw_text: str) -> dict | None:
    cleaned = re.sub(r"```(?:json)?|```", "", raw_text).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _has_urdu_script(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


def _normalize_urdu_pronunciation(text: str) -> str:
    no_latin = re.sub(r"[A-Za-z0-9]+", " ", text)
    no_symbols = re.sub(r"[“”\"'`~@#$%^&*_+=<>|/\\\[\]()]+", " ", no_latin)
    cleaned = re.sub(r"\s*،\s*", "، ", no_symbols)
    cleaned = re.sub(r"\s*[.۔]+\s*", "۔ ", cleaned)
    cleaned = re.sub(r"\s*[؟?]+\s*", "؟ ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _build_dynamic_tags(raw_tags: object, topic: str, title: str, sections: list[dict]) -> list[str]:
    tags: list[str] = []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            s = str(t).replace("#", "").strip()
            if s and len(s) <= 45 and s not in tags:
                tags.append(s)

    combined = f"{topic} {title} " + " ".join(x.get("text", "") for x in sections)
    c_low = combined.lower()

    topic_specific: list[str] = []
    if "dajjal" in c_low or "دجال" in combined:
        topic_specific += ["Dajjal", "Fitna Dajjal", "Dajjal In Islam", "دجال کا فتنہ", "دجال"]
    if "yajooj" in c_low or "majooj" in c_low or "یاجوج" in combined or "ماجوج" in combined:
        topic_specific += ["Yajooj Majooj", "Gog and Magog", "یاجوج ماجوج", "یاجوج ماجوج کا واقعہ"]
    if "aakhri" in c_low or "akhri" in c_low or "آخری زمانہ" in combined or "قیامت" in combined:
        topic_specific += ["Akhri Zamana", "Aakhri Zamana", "آخری زمانہ", "قیامت کی نشانیاں"]
    if "hadees" in c_low or "hadith" in c_low or "حدیث" in combined:
        topic_specific += ["Hadees", "Hadees Sharif", "حدیث نبوی", "حدیث پاک"]
    if "nabi" in c_low or "nabiyon" in c_low or "نبی" in combined or "انبیاء" in combined:
        topic_specific += ["Nabiyon Ke Waqiat", "Prophet Stories Urdu", "انبیاء کے واقعات", "نبیوں کے سچے واقعات"]
    if "sahaba" in c_low or "صحابی" in combined or "صحابہ" in combined:
        topic_specific += ["Sahaba Ke Waqiat", "Sahaba Stories Urdu", "صحابہ کے واقعات", "صحابہ کے سچے واقعات"]

    urdu_words = re.findall(r"[\u0600-\u06FF]{3,14}", " ".join(x.get("text", "") for x in sections[:2]))
    for uw in urdu_words[:5]:
        if uw not in topic_specific:
            topic_specific.append(uw)

    viral_reach_tags = [
        "Storybox",
        "Islamic Shorts",
        "Urdu Islamic Shorts",
        "Islamic Reminder",
        "Urdu Waqiat",
        "Emotional Islamic Shorts",
        "اسلامک شارٹس",
        "اردو واقعات",
        "Shorts",
    ]

    for item in topic_specific + viral_reach_tags:
        clean_item = item.replace("#", "").strip()
        if clean_item and len(clean_item) <= 45 and clean_item not in tags:
            tags.append(clean_item)

    final_tags: list[str] = []
    total_len = 0
    for tag in tags[:20]:
        if total_len + len(tag) + 1 <= 460:
            final_tags.append(tag)
            total_len += len(tag) + 1
    return final_tags


def _list_available_gemini_models(api_key: str) -> list[str]:
    encoded_key = urllib.parse.quote(api_key)
    for base in (
        f"https://generativelanguage.googleapis.com/v1beta/models?key={encoded_key}",
        f"https://generativelanguage.googleapis.com/v1/models?key={encoded_key}",
    ):
        req = urllib.request.Request(base, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            names: list[str] = []
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods") or []
                full_name = str(m.get("name") or "")
                if not full_name:
                    continue
                if methods and "generateContent" not in methods:
                    continue
                model_id = full_name.split("/")[-1]
                if "gemini" in model_id and "embedding" not in model_id and "imagen" not in model_id and "veo" not in model_id:
                    if model_id not in names:
                        names.append(model_id)
            if names:
                print(f"Discovered Gemini models: {', '.join(names[:8])}")
                return names
        except Exception as e:
            print(f"ListModels check failed ({base.split('?')[0]}): {e}")
    return []


def generate_lesson_with_gemini(api_key: str, history: dict) -> dict:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing; auto script generation cannot proceed.")

    used_ids = history.get("used_ids") or []
    recent_summaries = history.get("recent_summaries") or []

    chosen_topic = random.choice(TOPIC_POOL)
    chosen_hook = random.choice(HOOK_ANGLES)
    run_nonce = random.randint(100000, 999999)

    avoid_text = "\n".join(f"- {s}" for s in recent_summaries[-12:]) if recent_summaries else "- None yet"

    prompt = (
        f"Session #{run_nonce}. Write a high-retention 26-34 second vertical YouTube Short script in natural spoken URDU SCRIPT (اردو رسم الخط) "
        f"on topic: {chosen_topic}.\n"
        f"Opening rule: {chosen_hook}\n"
        "RULES:\n"
        "- Total ~72-84 Urdu words across 4 tight sections (~16-21 words each). No slow buildup or repetition.\n"
        "- Keep facts respectful and accurate for Dajjal, Yajooj Majooj, Aakhri Zamana, Hadees, Nabiyon ke sachay waqiat, and Sahaba ke achhay waqiat.\n"
        "- Use clear everyday Pakistani/Urdu words (وقت، دل، دن، رات، سکون، دعا، توبہ، یاد، نیکی، بھلائی، سچائی، ایمان، صبر) with zero English or Roman words in 'sections'.\n"
        "- Do NOT repeat any of the recent script summaries below.\n"
        "- Provide a punchy 'title' (under 75 chars), short 'thumb_text' (3-4 Urdu words), 12 'tags' (no '#'), and for each section give 'query' (2-3 English words) + 'sub_query' (2-3 English words).\n"
        "RECENT SCRIPTS TO AVOID:\n"
        f"{avoid_text}\n"
        "Output ONLY valid JSON:\n"
        "{\n"
        f'  "id": "sabaq_{run_nonce}",\n'
        '  "title": "پرکشش اردو عنوان",\n'
        '  "thumb_text": "تھمب نیل سرخی",\n'
        '  "tags": ["ٹیگ ایک", "Islamic Shorts"],\n'
        '  "summary": "Short 1-line summary of this specific script",\n'
        '  "sections": [\n'
        '    {"text": "اردو بات", "query": "stormy ocean dark", "sub_query": "dark clouds sky"}\n'
        "  ]\n"
        "}"
    )

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 1.0},
    }
    encoded_key = urllib.parse.quote(api_key)

    discovered = _list_available_gemini_models(api_key)
    candidate_models = discovered or [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest",
        "gemini-1.5-flash",
    ]

    endpoints: list[str] = []
    for model_id in candidate_models:
        endpoints.append(f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={encoded_key}")
        endpoints.append(f"https://generativelanguage.googleapis.com/v1/models/{model_id}:generateContent?key={encoded_key}")

    payload = None
    last_err = None
    for url in endpoints:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                break
        except Exception as e:
            last_err = e
            print(f"Endpoint failed ({url.split('?')[0]}): {e}")

    if not payload:
        raise RuntimeError(f"All Gemini endpoints failed: {last_err}")

    parts = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    text_out = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    parsed = _extract_json_object(text_out)
    if not parsed:
        raise RuntimeError("Gemini did not return valid JSON script.")

    sections = parsed.get("sections")
    if not isinstance(sections, list) or len(sections) < 3:
        raise RuntimeError("Gemini returned insufficient script sections.")

    valid_sections = []
    for item in sections[:4]:
        if isinstance(item, dict) and item.get("text") and item.get("query"):
            txt = _normalize_urdu_pronunciation(str(item["text"]))
            if not _has_urdu_script(txt):
                raise RuntimeError("Gemini script section is not in Urdu script.")
            valid_sections.append({
                "text": txt,
                "query": str(item["query"]).strip(),
                "sub_query": str(item.get("sub_query") or item.get("backup") or "dark clouds sky").strip(),
            })

    if len(valid_sections) < 3:
        raise RuntimeError("Not enough valid Urdu sections generated by Gemini.")

    lesson_id = str(parsed.get("id") or f"sabaq_{run_nonce}")
    if lesson_id in used_ids:
        lesson_id = f"{lesson_id}_{random.randint(100, 999)}"

    raw_title = str(parsed.get("title") or "").strip()
    clean_title = re.sub(r"\s+", " ", raw_title).strip()
    title = clean_title if _has_urdu_script(clean_title) else "آخری زمانہ کی بات"

    raw_thumb = _normalize_urdu_pronunciation(str(parsed.get("thumb_text") or ""))
    thumb_text = raw_thumb if _has_urdu_script(raw_thumb) else _normalize_urdu_pronunciation(title.split("|")[0]).strip()

    tags = _build_dynamic_tags(parsed.get("tags"), chosen_topic, title, valid_sections)
    summary = str(parsed.get("summary") or chosen_topic).strip()
    print(f"Selected topic: {chosen_topic}")
    print(f"Generated title: {title}")
    print(f"Generated tags ({len(tags)}): {', '.join(tags)}")
    return {
        "id": lesson_id,
        "title": title,
        "thumb_text": thumb_text,
        "tags": tags,
        "summary": summary,
        "sections": valid_sections,
    }


def ensure_urdu_font(fonts_dir: Path) -> tuple[str, str]:
    fonts_dir.mkdir(parents=True, exist_ok=True)
    for font_name, url, filename in FONT_SOURCES:
        dest = fonts_dir / filename
        if dest.exists() and dest.stat().st_size > 20_000:
            return font_name, str(dest.resolve())
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp, open(dest, "wb") as out:
                out.write(resp.read())
            if dest.exists() and dest.stat().st_size > 20_000:
                return font_name, str(dest.resolve())
        except Exception as e:
            print(f"Font download failed for {font_name}: {e}")

    fallbacks = [
        ("Noto Naskh Arabic", "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"),
        ("Noto Nastaliq Urdu", "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf"),
        ("DejaVu Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for name, path in fallbacks:
        if os.path.exists(path):
            return name, str(Path(path).resolve())
    return "DejaVu Sans", ""


def _try_elevenlabs_tts(full_text: str, mp3_path: Path) -> bool:
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        return False
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip() or "pNInz6obpgDQGcFmaJgB"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{urllib.parse.quote(voice_id)}"
    payload = {
        "text": full_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.80,
            "style": 0.30,
            "use_speaker_boost": True,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp, open(mp3_path, "wb") as out:
            out.write(resp.read())
        if mp3_path.exists() and mp3_path.stat().st_size > 15_000:
            print("Voice engine: ElevenLabs multilingual_v2")
            return True
    except Exception as e:
        print(f"ElevenLabs TTS fallback to edge-tts: {e}")
    return False


async def _generate_edge_continuous_voice(full_text: str, mp3_path: Path) -> None:
    voice_name = os.getenv("EDGE_TTS_VOICE", "").strip() or "ur-PK-AsadNeural"
    communicate = edge_tts.Communicate(
        text=full_text,
        voice=voice_name,
        rate="+6%",
        pitch="-3Hz",
    )
    await communicate.save(str(mp3_path))


def build_continuous_voice(full_text: str, work_dir: Path, clean_wav: Path) -> float:
    clean_text = _normalize_urdu_pronunciation(full_text)
    raw_mp3 = work_dir / "full_narration.mp3"
    if not _try_elevenlabs_tts(clean_text, raw_mp3):
        print("Voice engine: edge-tts continuous Urdu narration")
        asyncio.run(_generate_edge_continuous_voice(clean_text, raw_mp3))

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_mp3),
        "-af",
        "highpass=f=70,lowpass=f=11000,volume=1.0",
        "-ar",
        "44100",
        "-ac",
        "1",
        str(clean_wav),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return get_media_duration(clean_wav)


def prepare_moody_music_track(duration_sec: float, work_dir: Path, out_wav: Path) -> bool:
    dur = max(10.0, round(duration_sec + 1.0, 2))
    fade_out_st = max(0.5, dur - 1.5)

    for local_path in LOCAL_MUSIC_CANDIDATES:
        if local_path.exists() and local_path.stat().st_size > 10_000:
            cmd = [
                "ffmpeg",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(local_path.resolve()),
                "-t",
                f"{dur}",
                "-af",
                f"highpass=f=85,lowpass=f=2400,volume=0.16,afade=t=in:st=0:d=1.0,afade=t=out:st={fade_out_st}:d=1.5",
                "-ar",
                "44100",
                "-ac",
                "1",
                str(out_wav),
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 10_000:
                print(f"Music source: local repo file '{local_path}'")
                return True

    shuffled_sources = list(MOODY_MUSIC_SOURCES)
    random.shuffle(shuffled_sources)
    for idx, src_url in enumerate(shuffled_sources):
        dl_path = work_dir / f"moody_track_{idx}.mp3"
        req = urllib.request.Request(src_url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp, open(dl_path, "wb") as out:
                out.write(resp.read())
            if dl_path.exists() and dl_path.stat().st_size > 100_000:
                start_offset = random.uniform(5.0, 25.0)
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-stream_loop",
                    "-1",
                    "-ss",
                    f"{start_offset:.2f}",
                    "-i",
                    str(dl_path),
                    "-t",
                    f"{dur}",
                    "-af",
                    f"highpass=f=85,lowpass=f=2400,volume=0.16,afade=t=in:st=0:d=1.0,afade=t=out:st={fade_out_st}:d=1.5",
                    "-ar",
                    "44100",
                    "-ac",
                    "1",
                    str(out_wav),
                ]
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if res.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 10_000:
                    print(f"Music source: downloaded track ({src_url})")
                    return True
        except Exception as e:
            print(f"Music download skipped ({src_url}): {e}")

    print("Music source: none")
    return False


def mix_voice_and_music(voice_wav: Path, music_wav: Path, has_music: bool, mixed_wav: Path) -> None:
    if not has_music or not music_wav.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(voice_wav), "-c:a", "pcm_s16le", str(mixed_wav)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(voice_wav),
        "-i",
        str(music_wav),
        "-filter_complex",
        "[0:a]volume=1.08[v];[1:a]volume=1.0[m];[v][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]",
        "-map",
        "[aout]",
        "-ar",
        "44100",
        "-ac",
        "1",
        str(mixed_wav),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get_media_duration(file_path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    return float(subprocess.check_output(cmd, text=True).strip())


def _discover_local_clips(used_local: set[Path]) -> list[Path]:
    found: list[Path] = []
    for folder in LOCAL_CLIP_DIRS:
        if folder.exists() and folder.is_dir():
            for ext in ("*.mp4", "*.mov", "*.mkv", "*.webm"):
                for p in sorted(folder.glob(ext)):
                    if p.is_file() and p.stat().st_size > 20_000 and p.resolve() not in used_local:
                        found.append(p.resolve())
    return found


def pick_local_clip(used_local: set[Path]) -> Path | None:
    candidates = _discover_local_clips(used_local)
    if not candidates:
        used_local.clear()
        candidates = _discover_local_clips(used_local)
    if not candidates:
        return None
    chosen = random.choice(candidates)
    used_local.add(chosen)
    return chosen


def fetch_pixabay_clip(query: str, api_key: str, used_urls: set[str]) -> str | None:
    if not api_key or not query:
        return None
    encoded_q = urllib.parse.quote(query)
    encoded_key = urllib.parse.quote(api_key)
    url = f"https://pixabay.com/api/videos/?key={encoded_key}&q={encoded_q}&per_page=10&safesearch=true"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for hit in data.get("hits", []):
                videos = hit.get("videos", {})
                candidates = []
                for key in ("large", "medium", "small", "tiny"):
                    info = videos.get(key) or {}
                    link = info.get("url")
                    if link:
                        h = info.get("height") or 0
                        w = info.get("width") or 0
                        candidates.append((link, h, w))
                candidates.sort(key=lambda item: (0 if item[1] >= item[2] else 1, -item[1]))
                for link, _, _ in candidates:
                    if link not in used_urls:
                        used_urls.add(link)
                        return link
    except Exception as e:
        print(f"Pixabay search failed for '{query}': {e}")
    return None


def download_file(url: str, dest: Path) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp, open(dest, "wb") as out:
            out.write(resp.read())
        return dest.exists() and dest.stat().st_size > 50_000
    except Exception as e:
        print(f"Download failed for {url}: {e}")
        return False


def build_fallback_clip(dest: Path, dur: float, idx: int) -> None:
    colors = ["0x0c1322", "0x151e30", "0x101827", "0x192236"]
    c = colors[idx % len(colors)]
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={c}:s=1080x1920:d={dur}",
        "-vf",
        "fps=30",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def edit_pro_clip(raw_path: Path, out_path: Path, dur: float, idx: int) -> bool:
    if idx % 2 == 0:
        crop_w, crop_h = 980, 1742
        x_expr = "(iw-ow)/2 + ((iw-ow)*0.16)*sin(t*0.65)"
        y_expr = "(ih-oh)/2"
    else:
        crop_w, crop_h = 970, 1724
        x_expr = "(iw-ow)/2"
        y_expr = "(ih-oh)/2 + ((ih-oh)*0.14)*cos(t*0.6)"

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=w={crop_w}:h={crop_h}:x='{x_expr}':y='{y_expr}',"
        "scale=1080:1920:flags=lanczos,"
        "eq=contrast=1.10:brightness=0.01:saturation=1.15,"
        f"trim=duration={dur},setpts=PTS-STARTPTS,fps=30"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(raw_path),
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 15_000


def _format_ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    hours = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = sec % 60
    return f"{hours}:{mins:02d}:{secs:05.2f}"


def _build_moving_caption_chunks(sections: list[dict], total_duration: float) -> list[dict]:
    word_weights: list[tuple[str, int]] = []
    for sec in sections:
        words = str(sec["text"]).strip().split()
        for i in range(0, len(words), 3):
            piece = " ".join(words[i : i + 3]).strip()
            if piece:
                word_weights.append((piece, max(1, len(words[i : i + 3]))))

    if not word_weights:
        return []

    total_w = sum(w for _, w in word_weights) or len(word_weights)
    chunks: list[dict] = []
    cursor = 0.0
    for idx, (piece, w) in enumerate(word_weights):
        if idx == len(word_weights) - 1:
            nxt = round(total_duration, 2)
        else:
            nxt = round(min(total_duration, cursor + (total_duration * w) / total_w), 2)
        if nxt > cursor:
            chunks.append({"text": piece, "start": round(cursor, 2), "end": nxt})
        cursor = nxt
    return chunks


def _render_ass_on_image_or_video(
    input_media: Path,
    output_media: Path,
    ass_text: str,
    ass_path: Path,
    font_file: str,
    is_still_image: bool = False,
) -> bool:
    ass_path.write_text(ass_text, encoding="utf-8")
    escaped_ass = str(ass_path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    fonts_dir = ""
    if font_file:
        fonts_dir = str(Path(font_file).parent).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    vf_sub = f"subtitles='{escaped_ass}'" + (f":fontsdir='{fonts_dir}'" if fonts_dir else "")
    cmd = ["ffmpeg", "-y", "-i", str(input_media), "-vf", vf_sub]
    if is_still_image:
        cmd += ["-frames:v", "1", "-q:v", "2", str(output_media)]
    else:
        cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "21", "-pix_fmt", "yuv420p", str(output_media)]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and output_media.exists() and output_media.stat().st_size > 2000


def generate_thumbnail(
    first_clip: Path,
    thumb_text: str,
    work_dir: Path,
    font_name: str,
    font_file: str,
) -> None:
    base_frame = work_dir / "thumb_base.png"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(first_clip),
            "-ss",
            "0.4",
            "-vframes",
            "1",
            "-vf",
            "scale=1080:1920,eq=contrast=1.18:brightness=-0.06:saturation=1.15",
            str(base_frame),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not base_frame.exists() or base_frame.stat().st_size < 2000:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x0b1021:s=1080x1920",
                "-vframes",
                "1",
                str(base_frame),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    clean_headline = thumb_text.replace("{", "").replace("}", "").strip() or "آخری زمانہ کا پیغام"
    ass_header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Thumb,{font_name},96,&H0000FFFF,&H0000FFFF,&H00000000,&HB0000000,"
        "-1,0,0,0,105,105,0,0,3,6,4,5,70,70,220,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:05.00,Thumb,,0,0,0,,{clean_headline}\n"
    )
    ok = _render_ass_on_image_or_video(
        base_frame,
        OUTPUT_THUMBNAIL,
        ass_header,
        work_dir / "thumb.ass",
        font_file,
        is_still_image=True,
    )
    if not ok:
        subprocess.run(["cp", "-f", str(base_frame), str(OUTPUT_THUMBNAIL)], check=False)


def burn_ass_captions(
    input_video: Path,
    output_video: Path,
    caption_chunks: list[dict],
    ass_path: Path,
    font_name: str,
    font_file: str,
) -> None:
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},82,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,4,3,2,55,55,370,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    for seg in caption_chunks:
        start_str = _format_ass_time(seg["start"])
        end_str = _format_ass_time(seg["end"])
        clean_txt = seg["text"].replace("{", "").replace("}", "").strip()
        events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{clean_txt}")

    ok = _render_ass_on_image_or_video(
        input_video,
        output_video,
        header + "\n".join(events) + "\n",
        ass_path,
        font_file,
        is_still_image=False,
    )
    if not ok:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(input_video), "-c:v", "copy", str(output_video)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _build_one_subclip(
    query_list: list[str],
    dur: float,
    idx: int,
    work_dir: Path,
    pixabay_key: str,
    used_urls: set[str],
    used_local: set[Path],
) -> Path:
    out_clip = work_dir / f"subclip_{idx:02d}.mp4"
    local_clip = pick_local_clip(used_local)
    if local_clip and edit_pro_clip(local_clip, out_clip, dur, idx):
        return out_clip

    for q in query_list:
        url = fetch_pixabay_clip(q, pixabay_key, used_urls)
        if url:
            raw_clip = work_dir / f"raw_{idx:02d}.mp4"
            if download_file(url, raw_clip):
                if edit_pro_clip(raw_clip, out_clip, dur, idx):
                    return out_clip

    build_fallback_clip(out_clip, dur, idx)
    return out_clip


def main() -> None:
    print("Starting islamic_reel.py...")
    work_dir = Path("build_assets")
    work_dir.mkdir(exist_ok=True)

    history = load_history()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()

    font_name, font_file = ensure_urdu_font(work_dir / "fonts")
    print(f"Using font: {font_name} ({font_file or 'system'})")

    lesson = generate_lesson_with_gemini(gemini_key, history)
    history.setdefault("used_ids", []).append(lesson["id"])
    history.setdefault("recent_summaries", []).append(lesson["summary"])
    save_history(history)

    sections = lesson["sections"]
    print(f"Generated lesson '{lesson['id']}' with {len(sections)} sections.")

    full_text = " ".join(x["text"].strip() for x in sections)
    full_voice_wav = work_dir / "full_voice.wav"
    total_voice_dur = max(12.0, round(build_continuous_voice(full_text, work_dir, full_voice_wav), 2))

    moody_music_wav = work_dir / "moody_music.wav"
    mixed_audio_wav = work_dir / "mixed_audio.wav"
    has_music = prepare_moody_music_track(total_voice_dur, work_dir, moody_music_wav)
    mix_voice_and_music(full_voice_wav, moody_music_wav, has_music, mixed_audio_wav)

    sec_word_counts = [max(4, len(x["text"].split())) for x in sections]
    total_words = sum(sec_word_counts) or len(sections)
    sec_durations: list[float] = []
    acc = 0.0
    for idx, wc in enumerate(sec_word_counts):
        if idx == len(sec_word_counts) - 1:
            d = max(2.4, round(total_voice_dur - acc, 2))
        else:
            d = max(2.4, round((total_voice_dur * wc) / total_words, 2))
            acc = round(acc + d, 2)
        sec_durations.append(d)

    used_urls: set[str] = set()
    used_local: set[Path] = set()
    edited_clips: list[Path] = []
    sub_idx = 0

    for item, sec_dur in zip(sections, sec_durations):
        q1 = item.get("query", "")
        q2 = item.get("sub_query", "")
        if sec_dur >= 5.5:
            half_a = round(sec_dur * 0.5, 2)
            half_b = max(1.8, round(sec_dur - half_a, 2))
            edited_clips.append(_build_one_subclip([q1, q2], half_a, sub_idx, work_dir, pixabay_key, used_urls, used_local))
            sub_idx += 1
            edited_clips.append(_build_one_subclip([q2, q1], half_b, sub_idx, work_dir, pixabay_key, used_urls, used_local))
            sub_idx += 1
        else:
            edited_clips.append(_build_one_subclip([q1, q2], sec_dur, sub_idx, work_dir, pixabay_key, used_urls, used_local))
            sub_idx += 1

    generate_thumbnail(edited_clips[0], lesson["thumb_text"], work_dir, font_name, font_file)

    clips_concat = work_dir / "clips_concat.txt"
    with open(clips_concat, "w", encoding="utf-8") as f:
        for c in edited_clips:
            f.write(f"file '{c.resolve()}'\n")

    merged_video = work_dir / "merged.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(clips_concat),
            "-c:v",
            "copy",
            str(merged_video),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    caption_chunks = _build_moving_caption_chunks(sections, total_voice_dur)
    captioned_video = work_dir / "captioned.mp4"
    ass_file = work_dir / "captions.ass"
    burn_ass_captions(merged_video, captioned_video, caption_chunks, ass_file, font_name, font_file)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(captioned_video),
            "-i",
            str(mixed_audio_wav),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(OUTPUT_VIDEO),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if not OUTPUT_VIDEO.exists() or OUTPUT_VIDEO.stat().st_size == 0:
        raise RuntimeError("Failed to generate final_islamic_short.mp4.")

    final_dur = get_media_duration(OUTPUT_VIDEO)
    meta = {
        "title": lesson["title"][:95],
        "description": (
            f"{full_text}\n\n"
            "#Storybox #IslamicShorts #AkhriZamana #UrduReminder #Shorts"
        ),
        "tags": lesson["tags"],
        "thumbnail_path": str(OUTPUT_THUMBNAIL) if OUTPUT_THUMBNAIL.exists() else "",
        "video_path": str(OUTPUT_VIDEO),
        "duration_seconds": round(final_dur, 2),
        "clips_count": len(edited_clips),
    }
    OUTPUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {OUTPUT_VIDEO} ({final_dur:.1f}s) and thumbnail successfully.")


if __name__ == "__main__":
    main()
