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

FALLBACK_LESSONS = [
    {
        "id": "sabaq_01_be_hissi",
        "title": "آخری زمانہ کا سبق: دل کی بے حسی | Islamic Short",
        "lines": [
            {"text": "آخری زمانے کا سب سے خطرناک حال یہ ہے کہ گناہ عام ہو جائیں اور دل کو بوجھ ہی نہ لگے۔", "query": "dark clouds", "backup": "rain night"},
            {"text": "ہم روز نئی خبریں، فتنے اور بے حیائی دیکھتے ہیں، مگر اندر سے بالکل سُن ہو جاتے ہیں۔", "query": "phone screen", "backup": "city lights"},
            {"text": "جب حق بات سن کر بھی اندر کوئی حرکت نہ ہو، تو سمجھ لیں دل کو علاج کی ضرورت ہے۔", "query": "hourglass sand", "backup": "clock time"},
            {"text": "آخری زمانے میں اصل امتحان مال یا طاقت کا نہیں، اپنے دل کو زندہ رکھنے کا ہے۔", "query": "spark dark", "backup": "candle flame"},
            {"text": "ہم مصروفیت کو عذر بنا لیتے ہیں، حالانکہ اصل کمی توجہ اور اخلاص کی ہوتی ہے۔", "query": "busy street", "backup": "crowd walking"},
            {"text": "جو چیز ہمیں اللہ سے دور کرے، وہ چاہے کتنی ہی عام کیوں نہ ہو، نقصان دہ ہے۔", "query": "fog road", "backup": "misty trees"},
            {"text": "آج کا سبق یہ ہے: دن میں کم از کم ایک بار اپنے دل سے پوچھیں کہ میں کس طرف جا رہا ہوں۔", "query": "open book", "backup": "notebook desk"},
            {"text": "صرف زبان سے توبہ کافی نہیں، عمل میں چھوٹا سا بدلاؤ بھی لانا پڑتا ہے۔", "query": "water hands", "backup": "quiet river"},
            {"text": "نماز کو آخری وقت پر ٹالنا چھوڑیں، کیونکہ وقت کسی کا انتظار نہیں کرتا۔", "query": "mosque dome", "backup": "morning light"},
            {"text": "اپنے دل کی حفاظت کریں، کیونکہ آخری زمانے میں سب سے قیمتی چیز سلامت دل ہے۔", "query": "sunrise sky", "backup": "peaceful nature"},
        ],
    },
    {
        "id": "sabaq_02_be_adabi_aur_shor",
        "title": "آخری زمانہ کا سبق: شور میں کھویا سکون | Islamic Short",
        "lines": [
            {"text": "آخری زمانے میں شور بہت بڑھ جائے گا، مگر سکون صرف انہی کو ملے گا جو رک کر سنیں گے۔", "query": "traffic night", "backup": "city crowd"},
            {"text": "ہر بات پر رائے دینا اور ہر جھگڑے میں کود پڑنا انسان کا سکون اور وقار دونوں کھا جاتا ہے۔", "query": "typing phone", "backup": "mobile dark"},
            {"text": "جب زبان بے لگام ہو جائے تو رشتے بھی ٹوٹتے ہیں اور دل کی نرمی بھی ختم ہوتی ہے۔", "query": "broken glass", "backup": "shadow wall"},
            {"text": "علم کا فائدہ تب ہے جب وہ اخلاق اور عاجزی میں نظر آئے، تکبر میں نہیں۔", "query": "ancient library", "backup": "books table"},
            {"text": "آخری زمانے میں دکھاوا اتنا بڑھ جائے گا کہ سچا عمل خاموشی سے چھپنے لگے گا۔", "query": "spotlight dark", "backup": "stage lights"},
            {"text": "خاموشی کمزوری نہیں، بعض اوقات سب سے مضبوط اور دانشمندانہ فیصلہ ہوتی ہے۔", "query": "mountain peak", "backup": "calm lake"},
            {"text": "آج کا سبق یہ ہے: غصے یا بحث کے وقت پہلے دس سیکنڈ رکیں، پھر بات کریں۔", "query": "clock ticking", "backup": "sand timer"},
            {"text": "جس بات کا کوئی فائدہ نہ ہو، وہاں خاموش رہنا ہی سب سے بڑی بچت ہے۔", "query": "forest path", "backup": "green leaves"},
            {"text": "اپنے گھر اور زبان میں نرمی لائیں، یہی چیز ماحول کو پر سکون بناتی ہے۔", "query": "warm lantern", "backup": "evening light"},
            {"text": "یاد رکھیں، اصل کامیابی شور مچانے میں نہیں، رب کو راضی کرنے میں ہے۔", "query": "golden horizon", "backup": "sun rays"},
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


def generate_lesson_with_gemini(api_key: str, used_ids: list[str]) -> dict | None:
    if not api_key:
        return None

    recent_list = ", ".join(used_ids[-15:]) if used_ids else "none"
    prompt = (
        "You are an Islamic mentor and short-form video editor scriptwriter for 30-38 second vertical YouTube Shorts in Urdu. "
        "Do NOT write a story or fictional character narrative. Write ONE direct, sharp, insightful 'Aakhri Zamana' (End Times) LESSON / REALIZATION in proper URDU SCRIPT (اردو رسم الخط), "
        "as if a wise mentor is speaking directly and naturally to the viewer, followed by a practical tip. "
        "CRITICAL RULES:\n"
        "- Write 'title' and every line's 'text' strictly in URDU SCRIPT (no Roman Urdu, no English sentences).\n"
        "- Provide 10 punchy lines (8 to 13 Urdu words each), total around 95-120 Urdu words.\n"
        "- Line 1: Hard-hitting hook about Aakhri Zamana.\n"
        "- Lines 2-7: Direct reality check & core lesson (why people drift, how it affects heart/life).\n"
        "- Lines 8-9: Practical action/tip the viewer can apply today.\n"
        "- Line 10: Strong closing takeaway.\n"
        "- For each line, give 'query' (1-2 visual English words for stock video) and 'backup' (1-2 alternative English words).\n"
        f"Avoid these previous IDs/themes: {recent_list}.\n"
        "Output ONLY valid JSON:\n"
        "{\n"
        '  "id": "unique_lesson_id",\n'
        '  "title": "اردو عنوان | Islamic Short",\n'
        '  "lines": [\n'
        '    {"text": "اردو جملہ", "query": "2 words", "backup": "2 words"}\n'
        "  ]\n"
        "}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={urllib.parse.quote(api_key)}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.85},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
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
        lines = parsed.get("lines")
        if not isinstance(lines, list) or len(lines) < 8:
            return None
        valid_lines = []
        for item in lines[:10]:
            if isinstance(item, dict) and item.get("text") and item.get("query"):
                txt = str(item["text"]).strip()
                if not _has_urdu_script(txt):
                    return None
                valid_lines.append({
                    "text": txt,
                    "query": str(item["query"]).strip(),
                    "backup": str(item.get("backup") or "nature sky").strip(),
                })
        if len(valid_lines) < 8:
            return None
        lesson_id = str(parsed.get("id") or f"sabaq_{random.randint(10000, 99999)}")
        raw_title = str(parsed.get("title") or "").strip()
        title = raw_title if _has_urdu_script(raw_title) else "آخری زمانہ کا سبق | Islamic Short"
        return {"id": lesson_id, "title": title, "lines": valid_lines}
    except Exception as e:
        print(f"Gemini lesson generation failed, using fallback: {e}")
        return None


def pick_lesson(used_ids: list[str], gemini_key: str) -> dict:
    lesson = generate_lesson_with_gemini(gemini_key, used_ids)
    if not lesson:
        unused = [x for x in FALLBACK_LESSONS if x["id"] not in used_ids]
        if not unused:
            used_ids.clear()
            unused = FALLBACK_LESSONS
        lesson = random.choice(unused)
    used_ids.append(lesson["id"])
    save_history(used_ids)
    return lesson


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


async def generate_voice_line(text: str, mp3_path: Path) -> None:
    communicate = edge_tts.Communicate(
        text=text,
        voice="ur-PK-AsadNeural",
        rate="+6%",
        pitch="-2Hz",
    )
    await communicate.save(str(mp3_path))


def process_voice_line(raw_mp3: Path, clean_wav: Path, pause_sec: float = 0.22) -> float:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_mp3),
        "-af",
        f"highpass=f=80,lowpass=f=12000,acompressor=threshold=-18dB:ratio=3:attack=10:release=120,loudnorm=I=-15:TP=-1.5:LRA=9,apad=pad_dur={pause_sec}",
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


def fetch_pixabay_clip(query: str, api_key: str, used_urls: set[str]) -> str | None:
    if not api_key or not query:
        return None
    encoded_q = urllib.parse.quote(query)
    encoded_key = urllib.parse.quote(api_key)
    url = f"https://pixabay.com/api/videos/?key={encoded_key}&q={encoded_q}&per_page=8&safesearch=true"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for hit in data.get("hits", []):
                videos = hit.get("videos", {})
                candidates = []
                for key in ("medium", "small", "large", "tiny"):
                    info = videos.get(key) or {}
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
        with urllib.request.urlopen(req, timeout=20) as resp, open(dest, "wb") as out:
            out.write(resp.read())
        return dest.exists() and dest.stat().st_size > 40_000
    except Exception as e:
        print(f"Download failed for {url}: {e}")
        return False


def build_fallback_clip(dest: Path, dur: float, idx: int) -> None:
    colors = ["0x0f172a", "0x1e293b", "0x111827", "0x172554", "0x1f2937"]
    c = colors[idx % len(colors)]
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={c}:s=1080x1920:d={dur}",
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
    # Punchy editor motion: alternating scale/crop framing + dynamic push/pull + warm/moody grade
    if idx % 4 == 0:
        crop_w, crop_h = 900, 1600
        x_expr = "(iw-ow)/2 + ((iw-ow)/4)*sin(t*0.8)"
        y_expr = "(ih-oh)*0.45"
    elif idx % 4 == 1:
        crop_w, crop_h = 840, 1493
        x_expr = "(iw-ow)/2"
        y_expr = "(ih-oh)/2 + ((ih-oh)/5)*cos(t*0.7)"
    elif idx % 4 == 2:
        crop_w, crop_h = 940, 1671
        x_expr = "(iw-ow)*0.35 + ((iw-ow)*0.2)*sin(t*0.9)"
        y_expr = "(ih-oh)*0.4"
    else:
        crop_w, crop_h = 860, 1529
        x_expr = "(iw-ow)*0.6 - ((iw-ow)*0.2)*sin(t*0.75)"
        y_expr = "(ih-oh)*0.5"

    vf = (
        "scale=1280:2276:force_original_aspect_ratio=increase,"
        f"crop=w={crop_w}:h={crop_h}:x='{x_expr}':y='{y_expr}',"
        "scale=1080:1920:flags=lanczos,"
        "eq=contrast=1.10:brightness=0.01:saturation=1.14,"
        "vignette=PI/4.5,"
        f"trim=duration={dur},setpts=PTS-STARTPTS,fps=30"
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
        "ultrafast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 10_000


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
        f"Style: Default,{font_name},62,&H00FFFFFF,&H0000FFFF,&H00000000,&HA0000000,"
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
        "ultrafast",
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

    font_name, font_file = ensure_urdu_font(work_dir / "fonts")
    lesson = pick_lesson(used_ids, gemini_key)
    lines = lesson["lines"]

    voice_wavs: list[Path] = []
    line_durations: list[float] = []

    for idx, item in enumerate(lines):
        raw_mp3 = work_dir / f"line_{idx:02d}.mp3"
        clean_wav = work_dir / f"line_{idx:02d}.wav"
        asyncio.run(generate_voice_line(item["text"], raw_mp3))
        dur = process_voice_line(raw_mp3, clean_wav, pause_sec=0.22)
        dur = max(2.2, round(dur, 2))
        voice_wavs.append(clean_wav)
        line_durations.append(dur)

    audio_concat = work_dir / "audio_concat.txt"
    with open(audio_concat, "w", encoding="utf-8") as f:
        for w in voice_wavs:
            f.write(f"file '{w.resolve()}'\n")

    full_voice_wav = work_dir / "full_voice.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(audio_concat),
            "-c:a",
            "pcm_s16le",
            str(full_voice_wav),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    used_urls: set[str] = set()
    edited_clips: list[Path] = []
    caption_segments: list[dict] = []
    cursor = 0.0

    for idx, (item, clip_dur) in enumerate(zip(lines, line_durations)):
        out_clip = work_dir / f"clip_{idx:02d}.mp4"
        ok = False
        for q in (item.get("query", ""), item.get("backup", "")):
            url = fetch_pixabay_clip(q, pixabay_key, used_urls)
            if url:
                raw_clip = work_dir / f"raw_{idx:02d}.mp4"
                if download_file(url, raw_clip):
                    ok = edit_pro_clip(raw_clip, out_clip, clip_dur, idx)
                    if ok:
                        break
        if not ok:
            build_fallback_clip(out_clip, clip_dur, idx)

        edited_clips.append(out_clip)
        caption_segments.append({
            "text": item["text"],
            "start": cursor,
            "end": round(cursor + clip_dur, 2),
        })
        cursor = round(cursor + clip_dur, 2)

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

    captioned_video = work_dir / "captioned.mp4"
    ass_file = work_dir / "captions.ass"
    burn_ass_captions(merged_video, captioned_video, caption_segments, ass_file, font_name, font_file)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(captioned_video),
            "-i",
            str(full_voice_wav),
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
    full_text = " ".join(x["text"] for x in lines)
    meta = {
        "title": lesson["title"],
        "description": (
            f"{full_text}\n\n"
            "#IslamicShorts #AkhriZamana #UrduReminder #IslamicReminder #Shorts"
        ),
        "video_path": str(OUTPUT_VIDEO),
        "duration_seconds": round(final_dur, 2),
        "clips_count": len(edited_clips),
    }
    OUTPUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {OUTPUT_VIDEO} ({final_dur:.1f}s) with {len(edited_clips)} pro-cut clips & lesson narration.")


if __name__ == "__main__":
    main()
