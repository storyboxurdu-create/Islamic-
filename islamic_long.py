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

OUTPUT_VIDEO = Path("final_islamic_long.mp4")
OUTPUT_META = Path("long_meta.json")
OUTPUT_THUMBNAIL = Path("long_thumbnail.jpg")
HISTORY_FILE = Path("islamic_long_history.json")

MIN_STORY_SEC = 180.0  # Full 3+ minutes natural story voice
TARGET_CLIPS = 24  # Faster build + smooth 1920x1080 scenes

PROPHET_TOPICS = [
    "Hazrat Yousuf (AS) ka sabr, azmaish aur sabse dilchasp mukammal waqia Urdu mein",
    "Hazrat Musa (AS) aur Khidr (AS) ke safar ka sabse hairat angez aur dilchasp waqia Urdu mein",
    "Hazrat Ibrahim (AS) ki aazmaish, tawakkul aur sabse dilchasp mukammal waqia Urdu mein",
    "Hazrat Sulaiman (AS) ki hikmat, insaf aur sabse dilchasp mukammal waqia Urdu mein",
    "Hazrat Ayub (AS) ka sabr, dua aur sabse dilchasp mukammal waqia Urdu mein",
    "Hazrat Yunus (AS) ka waqia, tawbah aur sabse dilchasp mukammal kahani Urdu mein",
    "Hazrat Adam (AS) aur shuruati waqiat ka sabse dilchasp aur ibrat naak qissa Urdu mein",
    "Hazrat Dawood (AS) aur Jaloot ke muqable ka sabse dilchasp waqia Urdu mein",
]

DEFAULT_SCENE_QUERIES = [
    "ancient desert dunes wide",
    "ancient stone city landscape",
    "dark stormy clouds sky",
    "candle light dark room",
    "sunrise over mountain horizon",
    "quiet night stars sky",
    "flowing river sunlight",
    "mountain rock cliff",
    "calm ocean waves",
    "open book pages",
    "golden wheat field",
    "clear sky clouds",
]

TEXT_COLORS = [
    "0xFFD60A",  # Bold Gold
    "0x4ADE80",  # Bright Green
    "0x38BDF8",  # Bright Sky Blue
    "0xFB923C",  # Bold Orange
    "0xFFFFFF",  # Pure White
]

FONT_URLS = [
    "https://github.com/google/fonts/raw/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf",
    "https://github.com/google/fonts/raw/main/notonastaliqurdu/NotoNastaliqUrdu%5Bwght%5D.ttf",
]


def get_dur(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    )
    return float(out.strip())


def ensure_font(work: Path) -> Path:
    font_dir = work / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    dest = font_dir / "UrduBoldFont.ttf"
    if not dest.exists() or dest.stat().st_size < 20_000:
        for url in FONT_URLS:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=25) as resp, open(dest, "wb") as out:
                    out.write(resp.read())
                if dest.exists() and dest.stat().st_size > 20_000:
                    break
            except Exception as e:
                print(f"Font download note: {e}")

    if not dest.exists() or dest.stat().st_size < 20_000:
        for sys_font in [
            "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]:
            if os.path.exists(sys_font):
                return Path(sys_font)
    return dest


def escape_ff_text(txt: str) -> str:
    cleaned = re.sub(r"[\r\n]+", " ", txt).strip()
    cleaned = cleaned.replace("\\", "\\\\")
    cleaned = cleaned.replace("'", "\u2019")
    cleaned = cleaned.replace(":", "\\:")
    cleaned = cleaned.replace("%", "\\%")
    cleaned = cleaned.replace("[", "\\[").replace("]", "\\]")
    return cleaned


def extract_json(raw_text: str) -> dict | None:
    cleaned = re.sub(r"```(?:json)?|```", "", raw_text).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def list_gemini_models(api_key: str) -> list[str]:
    enc_key = urllib.parse.quote(api_key)
    for base in (
        f"https://generativelanguage.googleapis.com/v1beta/models?key={enc_key}",
        f"https://generativelanguage.googleapis.com/v1/models?key={enc_key}",
    ):
        try:
            req = urllib.request.Request(base, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            found: list[str] = []
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods") or []
                name = str(m.get("name") or "")
                if not name or (methods and "generateContent" not in methods):
                    continue
                mid = name.split("/")[-1]
                if "gemini" in mid and "embedding" not in mid and "imagen" not in mid and "veo" not in mid:
                    if mid not in found:
                        found.append(mid)
            if found:
                return found
        except Exception as e:
            print(f"Model list warning: {e}")
    return []


def _call_gemini_raw(api_key: str, prompt: str, models: list[str]) -> str:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 1.0},
    }
    enc_key = urllib.parse.quote(api_key)
    urls: list[str] = []
    for mid in models:
        urls.append(f"https://generativelanguage.googleapis.com/v1beta/models/{mid}:generateContent?key={enc_key}")
        urls.append(f"https://generativelanguage.googleapis.com/v1/models/{mid}:generateContent?key={enc_key}")

    payload = None
    last_err = None
    for u in urls:
        try:
            req = urllib.request.Request(
                u,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=55) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                print(f"Gemini responded from: {u.split('?')[0]}")
                break
        except Exception as e:
            last_err = e

    if not payload:
        raise RuntimeError(f"Gemini request failed: {last_err}")

    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


def load_recent_titles() -> list[str]:
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return [str(x) for x in (data.get("recent_titles") or [])][-8:]
        except Exception:
            pass
    return []


def auto_generate_prophet_story(api_key: str) -> tuple[str, str, list[str], list[str], str]:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing in GitHub Secrets.")

    recent_titles = load_recent_titles()
    avoid_str = ", ".join(recent_titles) if recent_titles else "None"
    topic = random.choice(PROPHET_TOPICS)
    nonce = random.randint(100000, 999999)

    models = list_gemini_models(api_key) or [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest",
        "gemini-1.5-flash",
    ]

    prompt_part1 = (
        f"Unique Run ID #{nonce}. Write a COMPLETELY NEW and DIFFERENT Urdu story about: {topic}.\n"
        f"Do NOT repeat or closely copy these previous stories: {avoid_str}.\n"
        "Strict rules:\n"
        "- Write ONLY in natural spoken Urdu script (اردو رسم الخط), zero English or Roman words in story_part1 or title.\n"
        "- Write around 380 to 440 Urdu words for Part 1 (opening, characters, setting, rising events), ending at a natural sentence boundary.\n"
        "- Smooth prose only, no markdown or bullets.\n"
        "- Include 12 short 2-3 word English stock video queries in queries.\n"
        "Output ONLY valid JSON:\n"
        "{\n"
        '  "title": "نیا دلچسپ اردو عنوان",\n'
        '  "story_part1": "پہلا حصہ یہاں",\n'
        '  "tags": ["نبیوں کے واقعات", "Islamic Story Urdu", "Urdu Waqiat", "Storybox"],\n'
        '  "queries": ["ancient desert dunes wide", "sunrise over mountain horizon"]\n'
        "}"
    )

    raw1 = _call_gemini_raw(api_key, prompt_part1, models)
    parsed1 = extract_json(raw1)
    if not parsed1:
        raise RuntimeError("Gemini Part 1 returned invalid JSON.")

    part1 = str(parsed1.get("story_part1") or "").strip()
    title = str(parsed1.get("title") or "").strip()[:95]
    if not title:
        raise RuntimeError("Gemini did not return a story title.")

    raw_tags = parsed1.get("tags")
    tags = [str(t).strip() for t in raw_tags if str(t).strip()][:15] if isinstance(raw_tags, list) else []
    if not tags:
        tags = ["نبیوں کے واقعات", "Islamic Story Urdu", "Urdu Waqiat", "Storybox"]

    raw_q = parsed1.get("queries")
    queries = [str(q).strip() for q in raw_q if str(q).strip()][:16] if isinstance(raw_q, list) else []
    if len(queries) < 6:
        queries = DEFAULT_SCENE_QUERIES

    prompt_part2 = (
        f"Unique Run ID #{nonce} Part 2. Continue and COMPLETE the exact story '{title}' to its full dramatic climax, "
        f"resolution, and heartfelt moral ending.\n"
        f"Ending of Part 1: {part1[-450:]}\n"
        "Strict rules:\n"
        "- Write ONLY in natural spoken Urdu script (اردو رسم الخط), zero English or Roman words in story_part2.\n"
        "- Write around 360 to 420 Urdu words for Part 2 so combined narration is ~750+ Urdu words (3+ minutes).\n"
        "- Smooth prose only, no markdown or bullets.\n"
        "Output ONLY valid JSON:\n"
        "{\n"
        '  "story_part2": "دوسرا اور مکمل اختتامی حصہ یہاں"\n'
        "}"
    )

    raw2 = _call_gemini_raw(api_key, prompt_part2, models)
    parsed2 = extract_json(raw2)
    part2 = str((parsed2 or {}).get("story_part2") or "").strip()
    if not part2:
        part2 = re.sub(r"```(?:json)?|```", "", raw2).strip()

    full_story = f"{part1} {part2}".strip()
    wc = len(full_story.split())
    if wc < 240:
        raise RuntimeError(f"Generated story too short ({wc} words).")

    print(f"NEW story generated: '{title}' | Words: {wc} | Topic: {topic}")
    return title, full_story, tags, queries, topic


async def make_tts_and_word_chunks(text: str, mp3_path: Path) -> list[tuple[float, str]]:
    voice = os.getenv("EDGE_TTS_VOICE", "").strip() or "ur-PK-AsadNeural"
    communicate = edge_tts.Communicate(text=text, voice=voice, rate="-6%")
    starts_and_words: list[tuple[float, str]] = []

    with open(mp3_path, "wb") as out:
        async for chunk in communicate.stream():
            ctype = chunk.get("type")
            if ctype == "audio":
                out.write(chunk["data"])
            elif ctype == "WordBoundary":
                offset_s = float(chunk.get("offset", 0)) / 10_000_000.0
                word = str(chunk.get("text") or "").strip()
                if word:
                    starts_and_words.append((offset_s, word))

    # Group 3 words at a time so each phrase ends strictly when the next group starts
    grouped: list[tuple[float, str]] = []
    for i in range(0, len(starts_and_words), 3):
        grp = starts_and_words[i : i + 3]
        phrase = " ".join(w for _, w in grp).strip()
        if phrase:
            grouped.append((round(grp[0][0], 2), phrase))
    return grouped


def build_sequential_segments(
    grouped_starts: list[tuple[float, str]],
    story_text: str,
    total_dur: float,
) -> list[dict]:
    if not grouped_starts:
        words = [w for w in re.split(r"\s+", story_text.strip()) if w]
        chunks = [" ".join(words[i : i + 3]) for i in range(0, len(words), 3)] or ["مکمل واقعہ"]
        step = total_dur / len(chunks)
        grouped_starts = [(round(i * step, 2), ch) for i, ch in enumerate(chunks)]

    segments: list[dict] = []
    for idx, (st, phrase) in enumerate(grouped_starts):
        st_c = max(0.0, min(st, max(0.0, total_dur - 0.15)))
        if idx + 1 < len(grouped_starts):
            en_c = max(st_c + 0.12, min(grouped_starts[idx + 1][0], total_dur))
        else:
            en_c = total_dur
        if en_c > st_c + 0.05:
            segments.append({"start": round(st_c, 2), "end": round(en_c, 2), "text": phrase})
    return segments


def make_color_clip(dest: Path, dur: float, idx: int) -> None:
    colors = ["0x0c1322", "0x151e30", "0x101827", "0x192236"]
    color = colors[idx % len(colors)]
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=1920x1080:d={dur:.2f}",
            "-vf",
            "fps=30,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ],
        check=True,
    )


def build_clip(query: str, api_key: str, dest: Path, dur: float, idx: int, used_urls: set[str]) -> Path:
    if idx % 2 == 0:
        vf = (
            "scale=2048:1152:force_original_aspect_ratio=increase,"
            "crop=w=1920:h=1080:x='(iw-ow)/2+((iw-ow)*0.4)*sin(t*0.35)':y='(ih-oh)/2',"
            "eq=contrast=1.08:saturation=1.12,fps=30,format=yuv420p"
        )
    else:
        vf = (
            "scale=2048:1152:force_original_aspect_ratio=increase,"
            "crop=w=1920:h=1080:x='(iw-ow)/2':y='(ih-oh)/2+((ih-oh)*0.4)*cos(t*0.35)',"
            "eq=contrast=1.08:saturation=1.12,fps=30,format=yuv420p"
        )

    if api_key:
        url = (
            f"https://pixabay.com/api/videos/?key={urllib.parse.quote(api_key)}"
            f"&q={urllib.parse.quote(query)}&per_page=10&safesearch=true"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for hit in data.get("hits", []):
                vids = hit.get("videos", {})
                for k in ("medium", "small", "large", "tiny"):
                    link = (vids.get(k) or {}).get("url")
                    if link and link not in used_urls:
                        used_urls.add(link)
                        raw = dest.with_suffix(".raw.mp4")
                        dl_req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(dl_req, timeout=20) as dresp, open(raw, "wb") as out:
                            out.write(dresp.read())
                        if raw.exists() and raw.stat().st_size > 40_000:
                            res = subprocess.run(
                                [
                                    "ffmpeg",
                                    "-y",
                                    "-stream_loop",
                                    "-1",
                                    "-i",
                                    str(raw),
                                    "-t",
                                    f"{dur:.2f}",
                                    "-vf",
                                    vf,
                                    "-an",
                                    "-c:v",
                                    "libx264",
                                    "-preset",
                                    "ultrafast",
                                    "-pix_fmt",
                                    "yuv420p",
                                    str(dest),
                                ]
                            )
                            if res.returncode == 0 and dest.exists() and dest.stat().st_size > 20_000:
                                return dest
        except Exception as e:
            print(f"Clip {idx} ({query}) fallback: {e}")

    make_color_clip(dest, dur, idx)
    return dest


def apply_captions_and_popups(
    input_video: Path,
    output_video: Path,
    segments: list[dict],
    font_path: Path,
    total_dur: float,
    work: Path,
) -> Path:
    font_str = str(font_path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")
    filter_parts: list[str] = []

    # Thick dark bar at bottom so large bold Urdu text always stands out clearly
    filter_parts.append("drawbox=x=0:y=ih-195:w=iw:h=195:color=black@0.72:t=fill")

    # Each segment starts right when the previous ends (no overlap) and glides horizontally
    for idx, seg in enumerate(segments):
        st = max(0.0, float(seg["start"]))
        en = min(total_dur, float(seg["end"]))
        if en <= st:
            continue
        col = TEXT_COLORS[idx % len(TEXT_COLORS)]
        txt_esc = escape_ff_text(seg["text"])
        if not txt_esc:
            continue

        # Smooth moving motion across bottom bar during this exact phrase window
        dur_s = max(0.1, en - st)
        x_expr = f"max(80\\, min(w-tw-80\\, (w-tw)/2 + 65*sin(((t-{st:.2f})/{dur_s:.2f})*3.14159)))"
        y_expr = "h-145"
        filter_parts.append(
            f"drawtext=fontfile='{font_str}':text='{txt_esc}':"
            f"fontcolor={col}:fontsize=74:borderw=5:bordercolor=black@0.95:"
            f"shadowcolor=black@0.85:shadowx=3:shadowy=3:"
            f"x={x_expr}:y={y_expr}:enable='between(t,{st:.2f},{en:.2f})'"
        )

    # Bold Subscribe + Bell icon pop-up (box and text share exact same x/y coordinates)
    popup_windows = [(40.0, 47.0), (105.0, 112.0), (155.0, 162.0)]
    box_w, box_h = 620, 104
    bell_text = escape_ff_text("🔔 SUBSCRIBE & BELL")
    for p_start, p_end in popup_windows:
        if p_start + 1.0 < total_dur:
            p_end_c = min(p_end, max(p_start + 1.0, total_dur - 0.5))
            # Slide in from right edge to (w - box_w - 50), then pulse slightly
            x_box_expr = (
                f"if(lt(t-{p_start:.2f},0.4), "
                f"w - ((t-{p_start:.2f})/0.4)*({box_w}+50), "
                f"w-{box_w}-50 + 8*sin((t-{p_start:.2f})*8))"
            )
            y_box_expr = "46"
            filter_parts.append(
                f"drawbox=x='{x_box_expr}':y='{y_box_expr}':w={box_w}:h={box_h}:"
                f"color=0xDC2626@0.96:t=fill:enable='between(t,{p_start:.2f},{p_end_c:.2f})'"
            )
            filter_parts.append(
                f"drawbox=x='{x_box_expr}':y='{y_box_expr}':w={box_w}:h={box_h}:"
                f"color=white@0.9:t=4:enable='between(t,{p_start:.2f},{p_end_c:.2f})'"
            )
            x_txt_expr = f"({x_box_expr}) + 32"
            y_txt_expr = f"({y_box_expr}) + 24"
            filter_parts.append(
                f"drawtext=fontfile='{font_str}':text='{bell_text}':"
                f"fontcolor=0xFDE047:fontsize=46:borderw=4:bordercolor=black@0.95:"
                f"x='{x_txt_expr}':y='{y_txt_expr}':enable='between(t,{p_start:.2f},{p_end_c:.2f})'"
            )

    script_file = work / "vf_chain.txt"
    script_file.write_text(",\n".join(filter_parts) + "\n", encoding="utf-8")

    res = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_video),
            "-filter_complex_script",
            str(script_file),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(output_video),
        ]
    )
    if res.returncode != 0 or not output_video.exists() or output_video.stat().st_size < 20_000:
        print(f"Overlay render fallback (returncode={res.returncode}), using base merged video.")
        return input_video
    return output_video


def prepare_soft_bg_audio(voice_wav: Path, dur: float, work: Path) -> Path:
    bg_wav = work / "soft_bg.wav"
    mixed_wav = work / "final_mix.wav"
    fade_out_at = max(1.0, dur - 2.5)
    bg_res = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=110:duration={dur:.2f}",
            "-af",
            f"lowpass=f=260,volume=0.04,afade=t=in:st=0:d=2.0,afade=t=out:st={fade_out_at:.2f}:d=2.5",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(bg_wav),
        ]
    )
    if bg_res.returncode == 0 and bg_wav.exists() and bg_wav.stat().st_size > 10_000:
        mix_res = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(voice_wav),
                "-i",
                str(bg_wav),
                "-filter_complex",
                "[0:a]volume=1.08[v];[1:a]volume=1.0[m];[v][m]amix=inputs=2:duration=first:normalize=0[aout]",
                "-map",
                "[aout]",
                "-ar",
                "44100",
                "-ac",
                "1",
                str(mixed_wav),
            ]
        )
        if mix_res.returncode == 0 and mixed_wav.exists() and mixed_wav.stat().st_size > 10_000:
            return mixed_wav
    return voice_wav


def create_clean_thumbnail(first_clip: Path, title: str, font_path: Path, work: Path) -> None:
    base_png = work / "thumb_raw.png"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(first_clip),
            "-ss",
            "0.5",
            "-vframes",
            "1",
            "-vf",
            "scale=1280:720,eq=contrast=1.15:brightness=-0.05",
            str(base_png),
        ],
        check=False,
    )
    if not base_png.exists() or base_png.stat().st_size < 2000:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0b1021:s=1280x720", "-vframes", "1", str(base_png)],
            check=True,
        )

    font_str = str(font_path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")
    thumb_txt = escape_ff_text(title[:45])
    res = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(base_png),
            "-vf",
            f"drawbox=x=0:y=ih-150:w=iw:h=150:color=black@0.75:t=fill,"
            f"drawtext=fontfile='{font_str}':text='{thumb_txt}':fontcolor=0xFFD60A:fontsize=54:"
            f"borderw=4:bordercolor=black@0.95:x=(w-tw)/2:y=h-108",
            "-q:v",
            "2",
            str(OUTPUT_THUMBNAIL),
        ]
    )
    if res.returncode != 0 or not OUTPUT_THUMBNAIL.exists():
        subprocess.run(["ffmpeg", "-y", "-i", str(base_png), "-q:v", "2", str(OUTPUT_THUMBNAIL)], check=False)


def main() -> None:
    work = Path("build_long_assets")
    work.mkdir(exist_ok=True)

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()

    font_path = ensure_font(work)
    print(f"Using font file: {font_path}")

    title, story_text, tags, queries, topic = auto_generate_prophet_story(gemini_key)

    mp3 = work / "voice.mp3"
    wav = work / "voice.wav"
    grouped_starts = asyncio.run(make_tts_and_word_chunks(story_text, mp3))

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3), "-ar", "44100", "-ac", "1", str(wav)],
        check=True,
    )

    actual_voice_dur = get_dur(wav)
    if actual_voice_dur < MIN_STORY_SEC:
        raise RuntimeError(
            f"Generated story voice is only {actual_voice_dur:.1f}s (< {MIN_STORY_SEC:.0f}s). "
            "Story length needs to be longer so narration itself is 3+ minutes."
        )

    segments = build_sequential_segments(grouped_starts, story_text, actual_voice_dur)
    print(f"Exact story narration duration: {actual_voice_dur:.1f}s | Non-overlapping segments: {len(segments)}")

    each_dur = round(actual_voice_dur / TARGET_CLIPS, 2)
    used_urls: set[str] = set()
    clips: list[Path] = []

    for i in range(TARGET_CLIPS):
        q = queries[i % len(queries)]
        c = build_clip(q, pixabay_key, work / f"clip_{i:02d}.mp4", each_dur, i, used_urls)
        clips.append(c)

    concat_txt = work / "concat.txt"
    concat_txt.write_text("\n".join(f"file '{c.resolve()}'" for c in clips), encoding="utf-8")

    merged = work / "merged.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c:v", "copy", str(merged)],
        check=True,
    )

    styled_video = work / "styled_video.mp4"
    video_source = apply_captions_and_popups(merged, styled_video, segments, font_path, actual_voice_dur, work)
    audio_source = prepare_soft_bg_audio(wav, actual_voice_dur, work)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_source),
            "-i",
            str(audio_source),
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
    )

    create_clean_thumbnail(clips[0], title, font_path, work)

    meta = {
        "title": title,
        "description": story_text + "\n\n#Storybox #IslamicStory #UrduWaqiat #IslamicReminder",
        "tags": tags,
        "thumbnail_path": str(OUTPUT_THUMBNAIL.resolve()),
        "video_path": str(OUTPUT_VIDEO.resolve()),
    }
    OUTPUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    prev = load_recent_titles()
    prev.append(title)
    HISTORY_FILE.write_text(
        json.dumps({"last_title": title, "last_topic": topic, "recent_titles": prev[-8:]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Generated 1920x1080 {OUTPUT_VIDEO} ({get_dur(OUTPUT_VIDEO):.1f}s) with bold captions, pop-ups & thumbnail.")


if __name__ == "__main__":
    main()
