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


def generate_lesson_with_gemini(api_key: str, used_ids: list[str]) -> dict:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing; auto script generation cannot proceed.")

    recent_list = ", ".join(used_ids[-20:]) if used_ids else "none"
    prompt = (
        "You are an engaging Urdu mentor speaking naturally on a 32-38 second vertical YouTube Short about 'Aakhri Zamana' (End Times). "
        "Do NOT write a story or fictional character narrative. Write ONE direct, natural, conversational 'Aakhri Zamana' realization/lesson in proper URDU SCRIPT (اردو رسم الخط), "
        "sounding like a thoughtful person talking smoothly without robotic textbook pauses, followed by a practical daily tip. "
        "CRITICAL RULES:\n"
        "- Write 'title' and every line's 'text' strictly in URDU SCRIPT (no Roman Urdu, no English sentences).\n"
        "- Provide 8 natural, smooth lines (9 to 14 Urdu words each), total around 85-110 Urdu words.\n"
        "- Avoid heavy mechanical punctuation inside a line so speech flows smoothly.\n"
        "- Line 1: Direct hook about Aakhri Zamana.\n"
        "- Lines 2-6: Clear reality check on heart, habits, and modern distractions.\n"
        "- Line 7: Practical daily habit/tip.\n"
        "- Line 8: Strong closing reminder.\n"
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

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9},
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

    lines = parsed.get("lines")
    if not isinstance(lines, list) or len(lines) < 6:
        raise RuntimeError("Gemini returned insufficient script lines.")

    valid_lines = []
    for item in lines[:8]:
        if isinstance(item, dict) and item.get("text") and item.get("query"):
            txt = str(item["text"]).strip()
            if not _has_urdu_script(txt):
                raise RuntimeError("Gemini script line is not in Urdu script.")
            valid_lines.append({
                "text": txt,
                "query": str(item["query"]).strip(),
                "backup": str(item.get("backup") or "nature sky").strip(),
            })

    if len(valid_lines) < 6:
        raise RuntimeError("Not enough valid Urdu lines generated by Gemini.")

    lesson_id = str(parsed.get("id") or f"auto_sabaq_{random.randint(10000, 99999)}")
    raw_title = str(parsed.get("title") or "").strip()
    title = raw_title if _has_urdu_script(raw_title) else "آخری زمانہ کا سبق | Islamic Short"
    return {"id": lesson_id, "title": title, "lines": valid_lines}


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


async def generate_continuous_voice(full_text: str, mp3_path: Path) -> None:
    communicate = edge_tts.Communicate(
        text=full_text,
        voice="ur-PK-AsadNeural",
        rate="+10%",
        pitch="-3Hz",
    )
    await communicate.save(str(mp3_path))


def process_continuous_voice(raw_mp3: Path, clean_wav: Path) -> float:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_mp3),
        "-af",
        "highpass=f=80,lowpass=f=12000,equalizer=f=160:width_type=o:width=1.4:g=3.0,acompressor=threshold=-16dB:ratio=2.5:attack=10:release=120,loudnorm=I=-15:TP=-1.5:LRA=9",
        "-ar",
        "44100",
        "-ac",
        "1",
        str(clean_wav),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return get_media_duration(clean_wav)


def build_ambient_music_track(duration_sec: float, out_wav: Path) -> None:
    # Audible, calm atmospheric pad (warm chord + gentle pulse) clearly audible beneath voice
    dur = max(10.0, round(duration_sec + 1.0, 2))
    fc = (
        f"sine=frequency=110:sample_rate=44100:duration={dur}[n1];"
        f"sine=frequency=146.83:sample_rate=44100:duration={dur}[n2];"
        f"sine=frequency=220:sample_rate=44100:duration={dur}[n3];"
        f"sine=frequency=293.66:sample_rate=44100:duration={dur}[n4];"
        "[n1][n2][n3][n4]amix=inputs=4:weights='0.45 0.35 0.30 0.20',"
        "lowpass=f=650,tremolo=f=0.35:d=0.25,volume=0.14,"
        f"afade=t=in:st=0:d=1.2,afade=t=out:st={max(0.5, dur - 1.5)}:d=1.5"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-filter_complex",
        fc,
        "-ar",
        "44100",
        "-ac",
        "1",
        str(out_wav),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def mix_voice_and_music(voice_wav: Path, music_wav: Path, mixed_wav: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(voice_wav),
        "-i",
        str(music_wav),
        "-filter_complex",
        "[0:a]volume=1.10[v];[1:a]volume=1.0[m];[v][m]amix=inputs=2:duration=first:dropout_transition=2,loudnorm=I=-15:TP=-1.5:LRA=10[aout]",
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
    # Minimal zoom (wide 9:16 framing) with subtle smooth motion so video doesn't look overly zoomed
    if idx % 2 == 0:
        crop_w, crop_h = 1020, 1813
        x_expr = "(iw-ow)/2 + ((iw-ow)*0.15)*sin(t*0.6)"
        y_expr = "(ih-oh)/2"
    else:
        crop_w, crop_h = 1000, 1778
        x_expr = "(iw-ow)/2"
        y_expr = "(ih-oh)/2 + ((ih-oh)*0.15)*cos(t*0.6)"

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=w={crop_w}:h={crop_h}:x='{x_expr}':y='{y_expr}',"
        "scale=1080:1920:flags=lanczos,"
        "eq=contrast=1.08:brightness=0.01:saturation=1.12,"
        "vignette=PI/5.5,"
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


def _build_moving_caption_chunks(lines: list[dict], total_duration: float) -> list[dict]:
    # Split each line into short 2-3 word chunks so subtitles keep changing dynamically with speech
    chunks: list[dict] = []
    weights: list[int] = []
    raw_texts: list[str] = []

    for item in lines:
        words = str(item["text"]).strip().split()
        if not words:
            continue
        for i in range(0, len(words), 3):
            piece = " ".join(words[i : i + 3]).strip()
            if piece:
                raw_texts.append(piece)
                weights.append(max(1, len(words[i : i + 3])))

    if not raw_texts:
        return []

    total_w = sum(weights) or len(raw_texts)
    cursor = 0.0
    for idx, (txt, w) in enumerate(zip(raw_texts, weights)):
        if idx == len(raw_texts) - 1:
            end_t = round(total_duration, 2)
        else:
            seg_dur = max(0.45, (total_duration * w) / total_w)
            end_t = round(min(total_duration, cursor + seg_dur), 2)
        if end_t > cursor:
            chunks.append({"text": txt, "start": round(cursor, 2), "end": end_t})
        cursor = end_t
    return chunks


def burn_ass_captions(
    input_video: Path,
    output_video: Path,
    caption_chunks: list[dict],
    ass_path: Path,
    font_name: str,
    font_file: str,
) -> None:
    # Larger, bold Urdu captions positioned cleanly with subtle slide/pop feel
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
        f"Style: Default,{font_name},84,&H00FFFFFF,&H0000FFFF,&H00000000,&HB0000000,"
        "-1,0,0,0,104,102,0,0,3,4,2,2,50,50,380,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events: list[str] = []
    for seg in caption_chunks:
        start_str = _format_ass_time(seg["start"])
        end_str = _format_ass_time(seg["end"])
        clean_txt = seg["text"].replace("{", "").replace("}", "").strip()
        # Subtle upward entrance movement so text feels active rather than static
        animated_txt = f"{{\\fad(80,60)\\move(540,1570,540,1535,0,160)}}{clean_txt}"
        events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{animated_txt}")

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
    print("Starting islamic_reel.py...")
    work_dir = Path("build_assets")
    work_dir.mkdir(exist_ok=True)

    used_ids = load_history()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()

    font_name, font_file = ensure_urdu_font(work_dir / "fonts")
    print(f"Using font: {font_name} ({font_file or 'system'})")

    lesson = generate_lesson_with_gemini(gemini_key, used_ids)
    used_ids.append(lesson["id"])
    save_history(used_ids)
    lines = lesson["lines"]
    print(f"Generated lesson '{lesson['id']}' with {len(lines)} lines.")

    full_text = " ".join(x["text"].strip() for x in lines)
    raw_mp3 = work_dir / "full_voice.mp3"
    full_voice_wav = work_dir / "full_voice.wav"
    asyncio.run(generate_continuous_voice(full_text, raw_mp3))
    total_voice_dur = process_continuous_voice(raw_mp3, full_voice_wav)
    total_voice_dur = max(12.0, round(total_voice_dur, 2))

    ambient_music_wav = work_dir / "ambient_music.wav"
    mixed_audio_wav = work_dir / "mixed_audio.wav"
    build_ambient_music_track(total_voice_dur, ambient_music_wav)
    mix_voice_and_music(full_voice_wav, ambient_music_wav, mixed_audio_wav)

    # Distribute total duration smoothly across clips based on word count
    word_counts = [max(3, len(x["text"].split())) for x in lines]
    total_words = sum(word_counts) or len(lines)
    line_durations: list[float] = []
    acc = 0.0
    for idx, wc in enumerate(word_counts):
        if idx == len(word_counts) - 1:
            d = max(1.8, round(total_voice_dur - acc, 2))
        else:
            d = max(1.8, round((total_voice_dur * wc) / total_words, 2))
            acc = round(acc + d, 2)
        line_durations.append(d)

    used_urls: set[str] = set()
    edited_clips: list[Path] = []

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

    caption_chunks = _build_moving_caption_chunks(lines, total_voice_dur)
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
    print(f"Generated {OUTPUT_VIDEO} ({final_dur:.1f}s) successfully.")


if __name__ == "__main__":
    main()
