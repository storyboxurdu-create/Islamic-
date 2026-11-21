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

FALLBACK_STORIES = [
    {
        "id": "urdu_story_01_waqt_aur_dil",
        "title": "آخری زمانہ کا قصہ: جب وقت ہاتھ سے نکل گیا | Islamic Short",
        "scenes": [
            {
                "text": "آخری زمانے کا سب سے بڑا دھوکہ یہ ہے کہ انسان سمجھتا ہے اس کے پاس ابھی بہت وقت ہے۔",
                "query": "hourglass sand time close up",
            },
            {
                "text": "بلال ایک محنتی نوجوان تھا جو دن رات موبائل اور اسکرینز میں مصروف رہتا تھا۔",
                "query": "man working laptop night desk",
            },
            {
                "text": "اذان ہوتی تو وہ کہتا، بس یہ کام مکمل کر لوں، پھر نماز پڑھ لوں گا۔",
                "query": "clock ticking evening light",
            },
            {
                "text": "گھر والوں کی بات بھی وہ ادھوری سنتا اور اپنی دنیا میں کھویا رہتا۔",
                "query": "person wearing headphones walking",
            },
            {
                "text": "پھر ایک دن اس کے قریبی دوست کے اچانک انتقال کی خبر آئی تو بلال سُن رہ گیا۔",
                "query": "rainy window dark mood",
            },
            {
                "text": "جنازے میں کھڑے ہو کر اسے پہلی بار احساس ہوا کہ دولت اور اسکرینز وہاں ساتھ نہیں جاتیں۔",
                "query": "cemetery trees peaceful morning",
            },
            {
                "text": "اس رات گھر آ کر اس نے وضو کیا اور پچھلی غفلتوں پر دل سے توبہ کی۔",
                "query": "water splashing hands wuzu",
            },
            {
                "text": "اس نے سمجھ لیا کہ فتنوں سے بچنے کا پہلا قدم اپنے وقت کو اللہ کے حوالے کرنا ہے۔",
                "query": "mosque courtyard peaceful light",
            },
            {
                "text": "آج کی عملی ٹپ یہ ہے: ہر نماز سے دس منٹ پہلے موبائل اور کام ایک طرف رکھ دیں۔",
                "query": "smartphone placed on table",
            },
            {
                "text": "نماز کے بعد صرف تین منٹ خاموشی سے بیٹھ کر اپنی نیت اور آخرت کا جائزہ لیں۔",
                "query": "person sitting quietly reflection",
            },
            {
                "text": "جب آپ وقت کا حق ادا کرتے ہیں تو اللہ دل میں سکون اور برکت ڈال دیتا ہے۔",
                "query": "sunrise rays over horizon",
            },
            {
                "text": "آج کا یہ چھوٹا سا قدم کل آپ کی نجات کا ذریعہ بن سکتا ہے۔",
                "query": "green leaves sunlight nature",
            },
        ],
    },
    {
        "id": "urdu_story_02_zuban_aur_fitna",
        "title": "آخری زمانہ میں ایک لفظ کا اثر | Islamic Short",
        "scenes": [
            {
                "text": "آخری زمانے میں اکثر لوگ بڑے گناہوں سے نہیں، بے احتیاطی کی باتوں سے پھسلتے ہیں۔",
                "query": "crowd walking city street",
            },
            {
                "text": "عائشہ کو ایک گروپ میں کسی کے خلاف سنی سنائی بات ملی اور اس نے بنا سوچے آگے بھیج دی۔",
                "query": "typing message phone screen",
            },
            {
                "text": "وہ بات آگے پھیلتی گئی اور ایک بے قصور انسان کی عزت اور رشتے متاثر ہوئے۔",
                "query": "broken glass shadow dark",
            },
            {
                "text": "جب عائشہ کو حقیقت کا پتہ چلا تو اسے بہت ندامت ہوئی کہ اس کی جلد بازی سے کیا نقصان ہوا۔",
                "query": "woman regret evening light",
            },
            {
                "text": "اس نے خود آگے بڑھ کر سچ واضح کیا اور جس کا دل دکھا تھا اس سے معافی مانگی۔",
                "query": "two people talking calm",
            },
            {
                "text": "آخری زمانے میں زبان اور فارورڈ بٹن دونوں ایک بڑی آزمائش ہیں۔",
                "query": "spark ember dark background",
            },
            {
                "text": "جو بات تحقیق اور ادب کے بغیر آگے بڑھائی جائے، وہ دل اور دلوں کے رشتے کمزور کرتی ہے۔",
                "query": "foggy road trees morning",
            },
            {
                "text": "اس کی عملی ٹپ یہ ہے: کوئی بھی بات آگے بھیجنے سے پہلے خود سے دو سوال پوچھیں۔",
                "query": "open book wooden table",
            },
            {
                "text": "پہلا سوال: کیا یہ بات سچ ہے؟ اور دوسرا سوال: کیا اس سے کسی کا دل تو نہیں دکھے گا؟",
                "query": "calm lake reflection sunset",
            },
            {
                "text": "اگر یقین نہ ہو یا دل دکھنے کا خدشہ ہو تو خاموشی اختیار کر لیں۔",
                "query": "quiet mountain peak clouds",
            },
            {
                "text": "زبان کی حفاظت انسان کو فتنوں سے بچاتی ہے اور دل کو نرم رکھتی ہے۔",
                "query": "lantern light warm night",
            },
            {
                "text": "اپنی بات اور کردار کو آج ہی سنوار لیں۔",
                "query": "golden hour sky trees",
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
        "You are an Islamic storytelling scriptwriter for 35-42 second vertical YouTube Shorts in natural Urdu. "
        "Write ONE engaging, emotional, and creative 'Aakhri Zamana' (End Times) story with a named character, a clear turning point, and a practical daily tip at the end. "
        "CRITICAL LANGUAGE RULE: Write 'title' and every scene's 'text' strictly in proper URDU SCRIPT (اردو رسم الخط). Do NOT use Roman Urdu or English sentences in 'text'. "
        "Keep every 'query' in simple English keywords (3-4 words) for stock video search. "
        f"Avoid these previous topic IDs/themes: {recent_list}. "
        "Output ONLY a valid JSON object (no markdown, no extra text) with this exact structure:\n"
        "{\n"
        '  "id": "unique_short_snake_case_id",\n'
        '  "title": "دلچسپ اردو عنوان | Islamic Short",\n'
        '  "scenes": [\n'
        '    {"text": "صاف اور روانی بھری اردو کا ایک جملہ (10 سے 15 الفاظ)", "query": "3-4 English stock video keywords"}\n'
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Include 12 scenes total so total narration is around 120-145 Urdu words (~35-42 seconds).\n"
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
                valid_scenes.append({
                    "text": scene_text,
                    "query": str(s["query"]).strip(),
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


async def generate_full_urdu_voice(text: str, mp3_path: Path) -> None:
    voices = ["ur-PK-AsadNeural", "ur-PK-UzmaNeural"]
    last_err: Exception | None = None
    for voice in voices:
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate="-6%",
                pitch="-1Hz",
            )
            await communicate.save(str(mp3_path))
            if mp3_path.exists() and mp3_path.stat().st_size > 2000:
                return
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err


def normalize_full_audio(raw_mp3: Path, clean_wav: Path) -> float:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_mp3),
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11",
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
    if not api_key:
        return None
    encoded_q = urllib.parse.quote(query)
    encoded_key = urllib.parse.quote(api_key)
    url = f"https://pixabay.com/api/videos/?key={encoded_key}&q={encoded_q}&per_page=8&safesearch=true"
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
    palette = ["0x0b192c", "0x102a43", "0x132a13", "0x1d1e2c", "0x1b263b"]
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
    zoom_expr = (
        "min(zoom+0.0007,1.11)" if idx % 2 == 0 else "if(eq(on,1),1.09,max(zoom-0.0007,1.0))"
    )
    vf = (
        "scale=1200:2134:force_original_aspect_ratio=increase,"
        "crop=1200:2134,"
        f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={max(1, int(round(clip_dur * 30)))}:s=1080x1920:fps=30,"
        "eq=contrast=1.05:brightness=0.01:saturation=1.08,"
        f"trim=duration={clip_dur},setpts=PTS-STARTPTS,"
        f"fade=t=in:st=0:d=0.2,fade=t=out:st={max(0.1, clip_dur - 0.2)}:d=0.2"
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
        "22",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 10_000


def _find_font_path() -> str | None:
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _wrap_caption_lines(text: str, max_chars: int = 30) -> list[str]:
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
    return lines[:3]


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def burn_captions(input_video: Path, output_video: Path, caption_segments: list[dict]) -> None:
    font_path = _find_font_path()
    font_arg = f":fontfile='{_escape_drawtext(font_path)}'" if font_path else ""

    filters: list[str] = [
        "drawbox=x=0:y=ih*0.66:w=iw:h=ih*0.24:color=black@0.45:t=fill"
    ]

    for seg in caption_segments:
        start = round(seg["start"], 2)
        end = round(seg["end"], 2)
        lines = _wrap_caption_lines(seg["text"], max_chars=28)
        if not lines:
            continue

        line_height = 72
        total_h = len(lines) * line_height
        base_y = int(1920 * 0.75) - (total_h // 2)

        for idx, line in enumerate(lines):
            safe_line = _escape_drawtext(line)
            y_pos = base_y + idx * line_height
            draw_cmd = (
                f"drawtext=text='{safe_line}'{font_arg}:"
                f"fontsize=50:fontcolor=white:"
                f"borderw=4:bordercolor=black@0.92:"
                f"shadowx=0:shadowy=3:shadowcolor=black@0.8:"
                f"x=(w-text_w)/2:y={y_pos}:"
                f"enable='between(t,{start},{end})'"
            )
            filters.append(draw_cmd)

    vf_chain = ",".join(filters)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_video),
        "-vf",
        vf_chain,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
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

    story = pick_story(used_ids, gemini_key)
    scenes = story["scenes"]

    full_narration = " ".join(s["text"] for s in scenes)
    raw_voice_mp3 = work_dir / "raw_voice.mp3"
    clean_voice_wav = work_dir / "clean_voice.wav"

    asyncio.run(generate_full_urdu_voice(full_narration, raw_voice_mp3))
    voice_dur = normalize_full_audio(raw_voice_mp3, clean_voice_wav)

    total_words = sum(max(1, len(s["text"].split())) for s in scenes)
    target_duration = max(32.0, round(voice_dur + 0.5, 2))

    used_urls: set[str] = set()
    normalized_clips: list[Path] = []
    caption_segments: list[dict] = []
    cursor_time = 0.0

    for idx, scene in enumerate(scenes):
        words_ratio = max(1, len(scene["text"].split())) / total_words
        scene_dur = max(2.2, round(target_duration * words_ratio, 2))
        norm_file = work_dir / f"scene_{idx:02d}.mp4"

        ok = False
        clip_url = fetch_pixabay_clip_for_query(scene["query"], pixabay_key, used_urls)
        if clip_url:
            raw_file = work_dir / f"raw_{idx:02d}.mp4"
            if download_file(clip_url, raw_file):
                ok = normalize_clip(raw_file, norm_file, scene_dur, idx)

        if not ok:
            build_fallback_clip(norm_file, scene_dur, idx)

        normalized_clips.append(norm_file)
        caption_segments.append({
            "text": scene["text"],
            "start": cursor_time,
            "end": round(cursor_time + scene_dur, 2),
        })
        cursor_time += scene_dur

    concat_list = work_dir / "clips.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in normalized_clips:
            f.write(f"file '{p.resolve()}'\n")

    merged_video = work_dir / "merged_video.mp4"
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
            "-t",
            str(target_duration),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            str(merged_video),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    captioned_video = work_dir / "captioned_video.mp4"
    burn_captions(merged_video, captioned_video, caption_segments)

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
            "160k",
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
    print(f"Generated {OUTPUT_VIDEO} ({final_dur:.1f}s) with {len(normalized_clips)} clips & Urdu narration.")


if __name__ == "__main__":
    main()
