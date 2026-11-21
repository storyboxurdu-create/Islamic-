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

FALLBACK_STORIES = [
    {
        "id": "urdu_story_01_waqt_aur_dil",
        "title": "آخری زمانہ کا قصہ: جب وقت ہاتھ سے نکل گیا | Islamic Short",
        "scenes": [
            {
                "text": "آخری زمانے کا سب سے بڑا دھوکہ یہ ہے کہ انسان سمجھتا ہے اس کے پاس ابھی بہت وقت ہے۔",
                "query": "hourglass sand",
                "backup_query": "clock time",
            },
            {
                "text": "بلال ایک محنتی نوجوان تھا جو دن رات موبائل اور اسکرینز میں مصروف رہتا تھا۔",
                "query": "man smartphone night",
                "backup_query": "laptop dark",
            },
            {
                "text": "اذان ہوتی تو وہ کہتا، بس یہ کام مکمل کر لوں، پھر نماز پڑھ لوں گا۔",
                "query": "wall clock",
                "backup_query": "evening desk",
            },
            {
                "text": "گھر والوں کی بات بھی وہ ادھوری سنتا اور اپنی دنیا میں کھویا رہتا۔",
                "query": "headphones walking",
                "backup_query": "city crowd",
            },
            {
                "text": "پھر ایک دن اس کے قریبی دوست کے اچانک انتقال کی خبر آئی تو بلال سُن رہ گیا۔",
                "query": "rain window",
                "backup_query": "dark clouds",
            },
            {
                "text": "جنازے میں کھڑے ہو کر اسے پہلی بار احساس ہوا کہ دولت اور اسکرینز وہاں ساتھ نہیں جاتیں۔",
                "query": "cemetery trees",
                "backup_query": "graveyard morning",
            },
            {
                "text": "اس رات گھر آ کر اس نے وضو کیا اور پچھلی غفلتوں پر دل سے توبہ کی۔",
                "query": "water hands",
                "backup_query": "washing hands",
            },
            {
                "text": "اس نے سمجھ لیا کہ فتنوں سے بچنے کا پہلا قدم اپنے وقت کو اللہ کے حوالے کرنا ہے۔",
                "query": "mosque dome",
                "backup_query": "mosque night",
            },
            {
                "text": "آج کی عملی ٹپ یہ ہے: ہر نماز سے دس منٹ پہلے موبائل اور کام ایک طرف رکھ دیں۔",
                "query": "phone table",
                "backup_query": "desk minimal",
            },
            {
                "text": "نماز کے بعد صرف تین منٹ خاموشی سے بیٹھ کر اپنی نیت اور آخرت کا جائزہ لیں۔",
                "query": "sitting meditation",
                "backup_query": "quiet prayer",
            },
            {
                "text": "جب آپ وقت کا حق ادا کرتے ہیں تو اللہ دل میں سکون اور برکت ڈال دیتا ہے۔",
                "query": "sunrise mountains",
                "backup_query": "morning sun",
            },
            {
                "text": "آج کا یہ چھوٹا سا قدم کل آپ کی نجات کا ذریعہ بن سکتا ہے۔",
                "query": "green leaves",
                "backup_query": "nature sunlight",
            },
        ],
    },
    {
        "id": "urdu_story_02_zuban_aur_fitna",
        "title": "آخری زمانہ میں ایک لفظ کا اثر | Islamic Short",
        "scenes": [
            {
                "text": "آخری زمانے میں اکثر لوگ بڑے گناہوں سے نہیں، بے احتیاطی کی باتوں سے پھسلتے ہیں۔",
                "query": "crowd walking",
                "backup_query": "busy street",
            },
            {
                "text": "عائشہ کو ایک گروپ میں کسی کے خلاف سنی سنائی بات ملی اور اس نے بنا سوچے آگے بھیج دی۔",
                "query": "typing phone",
                "backup_query": "mobile screen",
            },
            {
                "text": "وہ بات آگے پھیلتی گئی اور ایک بے قصور انسان کی عزت اور رشتے متاثر ہوئے۔",
                "query": "broken glass",
                "backup_query": "shadow wall",
            },
            {
                "text": "جب عائشہ کو حقیقت کا پتہ چلا تو اسے بہت ندامت ہوئی کہ اس کی جلد بازی سے کیا نقصان ہوا۔",
                "query": "sad woman",
                "backup_query": "evening window",
            },
            {
                "text": "اس نے خود آگے بڑھ کر سچ واضح کیا اور جس کا دل دکھا تھا اس سے معافی مانگی۔",
                "query": "people talking",
                "backup_query": "calm conversation",
            },
            {
                "text": "آخری زمانے میں زبان اور فارورڈ بٹن دونوں ایک بڑی آزمائش ہیں۔",
                "query": "fire sparks",
                "backup_query": "ember dark",
            },
            {
                "text": "جو بات تحقیق اور ادب کے بغیر آگے بڑھائی جائے، وہ دل اور دلوں کے رشتے کمزور کرتی ہے۔",
                "query": "fog forest",
                "backup_query": "misty trees",
            },
            {
                "text": "اس کی عملی ٹپ یہ ہے: کوئی بھی بات آگے بھیجنے سے پہلے خود سے دو سوال پوچھیں۔",
                "query": "open book",
                "backup_query": "notebook pen",
            },
            {
                "text": "پہلا سوال: کیا یہ بات سچ ہے؟ اور دوسرا سوال: کیا اس سے کسی کا دل تو نہیں دکھے گا؟",
                "query": "lake sunset",
                "backup_query": "calm water",
            },
            {
                "text": "اگر یقین نہ ہو یا دل دکھنے کا خدشہ ہو تو خاموشی اختیار کر لیں۔",
                "query": "mountain clouds",
                "backup_query": "high peaks",
            },
            {
                "text": "زبان کی حفاظت انسان کو فتنوں سے بچاتی ہے اور دل کو نرم رکھتی ہے۔",
                "query": "candle flame",
                "backup_query": "warm lantern",
            },
            {
                "text": "اپنی بات اور کردار کو آج ہی سنوار لیں۔",
                "query": "golden sunset",
                "backup_query": "sky clouds",
            },
        ],
    },
]


def load_history() -> list[str]:
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(x) for x in data]
            if isinstance(data, dict) and isinstance(data.get("used_ids"), list):
                return [str(x) for x in data["used_ids"]]
        except Exception:
            pass
    return []


def save_history(used_ids: list[str]) -> None:
    HISTORY_FILE.write_text(json.dumps(used_ids[-100:], ensure_ascii=False, indent=2), encoding="utf-8")


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


def generate_story_with_gemini(api_key: str, used_ids: list[str]) -> dict | None:
    if not api_key:
        return None

    recent_list = ", ".join(used_ids[-15:]) if used_ids else "none"
    prompt = (
        "You are an Islamic storytelling scriptwriter for 35-42 second vertical YouTube Shorts in natural, warm Urdu. "
        "Write ONE engaging, emotional, and creative 'Aakhri Zamana' (End Times) story with a named character, a clear turning point, and a practical daily tip at the end. "
        "CRITICAL LANGUAGE RULE: Write 'title' and every scene's 'text' strictly in proper URDU SCRIPT (اردو رسم الخط). Do NOT use Roman Urdu or English sentences in 'text'. "
        "For each scene, provide 'query' (1-2 simple visual English words, e.g. 'sand hourglass', 'rain window', 'mosque dome') and 'backup_query' (1-2 alternative visual English words). "
        f"Avoid these previous topic IDs/themes: {recent_list}. "
        "Output ONLY a valid JSON object (no markdown, no extra text) with this exact structure:\n"
        "{\n"
        '  "id": "unique_short_snake_case_id",\n'
        '  "title": "دلچسپ اردو عنوان | Islamic Short",\n'
        '  "scenes": [\n'
        '    {"text": "صاف اور قدرتی اردو جملہ (10 سے 14 الفاظ)", "query": "2 visual words", "backup_query": "2 backup words"}\n'
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Include 12 scenes total (~115-140 Urdu words total).\n"
        "- Scene 1: Strong hook about Aakhri Zamana in Urdu.\n"
        "- Scenes 2-7: A vivid, relatable story about a character facing a modern/end-times test and realizing the truth.\n"
        "- Scenes 8-11: Clear, actionable practical tip step-by-step.\n"
        "- Scene 12: Memorable closing reminder."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={urllib.parse.quote(api_key)}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        parts = (
            payload.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
        )
        text_out = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        parsed = _extract_json_object(text_out)
        if not parsed:
            return None
        scenes = parsed.get("scenes")
        if not isinstance(scenes, list) or len(scenes) < 10:
            return None
        valid_scenes = []
        for s in scenes[:12]:
            if isinstance(s, dict) and s.get("text") and s.get("query"):
                scene_text = str(s["text"]).strip()
                if not _has_urdu_script(scene_text):
                    return None
                q = str(s["query"]).strip()
                bq = str(s.get("backup_query") or "nature sky").strip()
                valid_scenes.append({
                    "text": scene_text,
                    "query": q,
                    "backup_query": bq,
                })
        if len(valid_scenes) < 10:
            return None
        story_id = str(parsed.get("id") or f"urdu_story_{random.randint(10000, 99999)}")
        raw_title = str(parsed.get("title") or "").strip()
        title = raw_title if _has_urdu_script(raw_title) else "آخری زمانہ کا قصہ اور عملی ٹپ | Islamic Short"
        return {"id": story_id, "title": title, "scenes": valid_scenes}
    except Exception as e:
        print(f"Gemini generation failed, using fallback story: {e}")
        return None


def pick_story(used_ids: list[str], gemini_key: str) -> dict:
    story = generate_story_with_gemini(gemini_key, used_ids)
    if not story:
        unused = [s for s in FALLBACK_STORIES if s["id"] not in used_ids]
        if not unused:
            used_ids.clear()
            unused = FALLBACK_STORIES
        story = random.choice(unused)

    used_ids.append(story["id"])
    save_history(used_ids)
    return story


def ensure_urdu_font(fonts_dir: Path) -> tuple[str, str]:
    fonts_dir.mkdir(parents=True, exist_ok=True)
    for font_name, url, filename in FONT_SOURCES:
        dest = fonts_dir / filename
        if dest.exists() and dest.stat().st_size > 20_000:
            return font_name, str(dest.resolve())
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp, open(dest, "wb") as out:
                out.write(resp.read())
            if dest.exists() and dest.stat().st_size > 20_000:
                return font_name, str(dest.resolve())
        except Exception as e:
            print(f"Font download failed for {font_name}: {e}")

    system_fallbacks = [
        ("Noto Naskh Arabic", "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"),
        ("Noto Nastaliq Urdu", "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf"),
        ("Noto Sans Arabic", "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"),
        ("DejaVu Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for name, path in system_fallbacks:
        if os.path.exists(path):
            return name, str(Path(path).resolve())
    return "DejaVu Sans", ""


async def generate_full_urdu_voice(text: str, mp3_path: Path) -> None:
    communicate = edge_tts.Communicate(
        text=text,
        voice="ur-PK-AsadNeural",
        rate="+2%",
        pitch="-3Hz",
    )
    await communicate.save(str(mp3_path))


def normalize_full_audio(raw_mp3: Path, clean_wav: Path) -> float:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_mp3),
        "-af",
        "highpass=f=75,lowpass=f=12500,loudnorm=I=-15:TP=-1.5:LRA=10",
        "-ar",
        "44100",
        "-ac",
        "1",
        str(clean_wav),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return get_media_duration(clean_wav)


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


def fetch_pixabay_clip_for_query(query: str, api_key: str, used_urls: set[str]) -> str | None:
    if not api_key or not query:
        return None
    encoded_q = urllib.parse.quote(query)
    encoded_key = urllib.parse.quote(api_key)
    url = f"https://pixabay.com/api/videos/?key={encoded_key}&q={encoded_q}&per_page=10&safesearch=true"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for hit in data.get("hits", []):
                videos = hit.get("videos", {})
                candidates = []
                for size_key in ("medium", "large", "small", "tiny"):
                    info = videos.get(size_key) or {}
                    link = info.get("url")
                    if link:
                        h = info.get("height") or 0
                        w = info.get("width") or 0
                        candidates.append((link, h, w))
                candidates.sort(key=lambda item: (0 if item[1] >= item[2] else 1, abs(item[1] - 1080)))
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
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as out:
            out.write(resp.read())
        return dest.exists() and dest.stat().st_size > 50_000
    except Exception as e:
        print(f"Download failed for {url}: {e}")
        return False


def build_fallback_clip(dest: Path, clip_dur: float, idx: int) -> None:
    palette = ["0x0c1821", "0x1b263b", "0x14281d", "0x1f1d2e", "0x241914"]
    color = palette[idx % len(palette)]
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=1080x1920:d={clip_dur}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def normalize_clip(raw_path: Path, out_path: Path, clip_dur: float, idx: int) -> bool:
    if idx % 3 == 0:
        zoom_expr = "min(zoom+0.0009,1.13)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih*0.42-(ih/zoom/2)"
    elif idx % 3 == 1:
        zoom_expr = "if(eq(on,1),1.12,max(zoom-0.0009,1.0))"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        zoom_expr = "min(zoom+0.0007,1.10)"
        x_expr = "iw*0.55-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    frames = max(1, int(round(clip_dur * 30)))
    vf = (
        "scale=1280:2276:force_original_aspect_ratio=increase,"
        "crop=1280:2276,"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s=1080x1920:fps=30,"
        "eq=contrast=1.08:brightness=0.01:saturation=1.12,"
        "vignette=PI/5,"
        f"trim=duration={clip_dur},setpts=PTS-STARTPTS"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 10_000


def merge_clips_with_crossfade(clips: list[Path], durations: list[float], out_video: Path, fade_dur: float = 0.35) -> None:
    if len(clips) == 1:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(clips[0]), "-c:v", "copy", str(out_video)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    inputs: list[str] = []
    for c in clips:
        inputs.extend(["-i", str(c)])

    filter_parts: list[str] = []
    prev_label = "[0:v]"
    cumulative_offset = 0.0

    for i in range(1, len(clips)):
        eff_dur = max(1.2, durations[i - 1])
        offset = max(0.1, round(cumulative_offset + eff_dur - fade_dur, 2))
        cumulative_offset = offset
        out_label = f"[v{i:02d}]" if i < len(clips) - 1 else "[vout]"
        filter_parts.append(
            f"{prev_label}[{i}:v]xfade=transition=fade:duration={fade_dur}:offset={offset}{out_label}"
        )
        prev_label = out_label

    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[vout]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        str(out_video),
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode != 0 or not out_video.exists():
        concat_list = out_video.parent / "fallback_concat.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for p in clips:
                f.write(f"file '{p.resolve()}'\n")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "21",
                "-pix_fmt",
                "yuv420p",
                str(out_video),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _format_ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    hours = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = sec % 60
    return f"{hours}:{mins:02d}:{secs:05.2f}"


def _wrap_urdu_lines(text: str, max_chars: int = 34) -> list[str]:
    words = text.strip().split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:2]


def burn_ass_captions(
    input_video: Path,
    output_video: Path,
    caption_segments: list[dict],
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
        f"Style: Default,{font_name},62,&H00FFFFFF,&H0000FFFF,&H00000000,&H96000000,"
        "-1,0,0,0,100,100,0,0,3,3,2,2,60,60,360,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    for seg in caption_segments:
        start_str = _format_ass_time(seg["start"])
        end_str = _format_ass_time(seg["end"])
        wrapped = "\\N".join(_wrap_urdu_lines(seg["text"], max_chars=34))
        clean_txt = wrapped.replace("{", "").replace("}", "")
        events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{clean_txt}")

    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")

    escaped_ass = str(ass_path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    fonts_dir = ""
    if font_file:
        fonts_dir = str(Path(font_file).parent).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    vf_sub = f"subtitles='{escaped_ass}'" + (f":fontsdir='{fonts_dir}'" if fonts_dir else "")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_video),
        "-vf",
        vf_sub,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        str(output_video),
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode != 0 or not output_video.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(input_video), "-c:v", "copy", str(output_video)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> None:
    work_dir = Path("build_assets")
    work_dir.mkdir(exist_ok=True)

    used_ids = load_history()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()

    font_name, font_file = ensure_urdu_font(work_dir / "fonts")
    story = pick_story(used_ids, gemini_key)
    scenes = story["scenes"]

    full_narration = " ".join(s["text"] for s in scenes)
    raw_voice_mp3 = work_dir / "raw_voice.mp3"
    clean_voice_wav = work_dir / "clean_voice.wav"

    asyncio.run(generate_full_urdu_voice(full_narration, raw_voice_mp3))
    voice_dur = normalize_full_audio(raw_voice_mp3, clean_voice_wav)

    total_words = sum(max(1, len(s["text"].split())) for s in scenes)
    target_duration = max(32.0, round(voice_dur + 0.4, 2))

    used_urls: set[str] = set()
    normalized_clips: list[Path] = []
    scene_durations: list[float] = []
    caption_segments: list[dict] = []
    cursor_time = 0.0

    for idx, scene in enumerate(scenes):
        words_ratio = max(1, len(scene["text"].split())) / total_words
        scene_dur = max(2.3, round(target_duration * words_ratio, 2))
        norm_file = work_dir / f"scene_{idx:02d}.mp4"

        ok = False
        for q in (scene.get("query", ""), scene.get("backup_query", "")):
            clip_url = fetch_pixabay_clip_for_query(q, pixabay_key, used_urls)
            if clip_url:
                raw_file = work_dir / f"raw_{idx:02d}.mp4"
                if download_file(clip_url, raw_file):
                    ok = normalize_clip(raw_file, norm_file, scene_dur, idx)
                    if ok:
                        break

        if not ok:
            build_fallback_clip(norm_file, scene_dur, idx)

        normalized_clips.append(norm_file)
        scene_durations.append(scene_dur)
        caption_segments.append({
            "text": scene["text"],
            "start": cursor_time,
            "end": round(cursor_time + scene_dur, 2),
        })
        cursor_time += scene_dur

    merged_video = work_dir / "merged_video.mp4"
    merge_clips_with_crossfade(normalized_clips, scene_durations, merged_video, fade_dur=0.35)

    captioned_video = work_dir / "captioned_video.mp4"
    ass_file = work_dir / "captions.ass"
    burn_ass_captions(merged_video, captioned_video, caption_segments, ass_file, font_name, font_file)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(captioned_video),
            "-i",
            str(clean_voice_wav),
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

    final_dur = get_media_duration(OUTPUT_VIDEO)
    meta = {
        "title": story["title"],
        "description": (
            f"{full_narration}\n\n"
            "#IslamicShorts #AkhriZamana #UrduReminder #IslamicReminder #Shorts"
        ),
        "video_path": str(OUTPUT_VIDEO),
        "duration_seconds": round(final_dur, 2),
        "clips_count": len(normalized_clips),
    }
    OUTPUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {OUTPUT_VIDEO} ({final_dur:.1f}s) using font '{font_name}' with {len(normalized_clips)} clips & crossfades.")


if __name__ == "__main__":
    main()
