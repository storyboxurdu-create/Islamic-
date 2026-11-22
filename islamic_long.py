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

MIN_STORY_SEC = 180.0  # Full 3+ minutes of natural story narration
TARGET_CLIPS = 32

PROPHET_TOPICS = [
    "Hazrat Yousuf (AS) ka sabr, azmaish aur sabse dilchasp mukammal waqia Urdu mein",
    "Hazrat Musa (AS) aur Khidr (AS) ke safar ka sabse hairat angez aur dilchasp waqia Urdu mein",
    "Hazrat Ibrahim (AS) ki aazmaish, tawakkul aur sabse dilchasp mukammal waqia Urdu mein",
    "Hazrat Sulaiman (AS) ki hikmat, insaf aur sabse dilchasp mukammal waqia Urdu mein",
    "Hazrat Ayub (AS) ka sabr, dua aur sabse dilchasp mukammal waqia Urdu mein",
    "Hazrat Yunus (AS) ka waqia, tawbah aur sabse dilchasp mukammal kahani Urdu mein",
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

CAPTION_ACCENTS = [
    "&H0000FFFF&",  # Golden Yellow
    "&H007CFF00&",  # Soft Mint/Lime
    "&H0055CCFF&",  # Warm Amber/Orange
    "&H00FFDD55&",  # Sky/Cyan glow
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
        "generationConfig": {"temperature": 0.95},
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
                break
        except Exception as e:
            last_err = e

    if not payload:
        raise RuntimeError(f"Gemini request failed: {last_err}")

    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


def auto_generate_prophet_story(api_key: str) -> tuple[str, str, list[str], list[str]]:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing in environment/secrets.")

    topic = random.choice(PROPHET_TOPICS)
    nonce = random.randint(10000, 99999)
    models = list_gemini_models(api_key) or [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest",
        "gemini-1.5-flash",
    ]

    prompt_part1 = (
        f"Run #{nonce} Part 1. Auto-generate the FIRST HALF of a vivid, dramatic, and deeply engaging Urdu story "
        f"about an interesting episode from the life of a Prophet ({topic}).\n"
        "Strict instructions:\n"
        "- Write ONLY in natural spoken Urdu script (اردو رسم الخط), with zero English or Roman words in story_part1 or title.\n"
        "- Write around 360 to 420 Urdu words for Part 1 (setting, characters, beginning, and rising tension), ending cleanly without cutting off mid-sentence.\n"
        "- Do not use bullet points or markdown inside story_part1; write smooth flowing Urdu prose ready for voiceover.\n"
        "- Provide 12 short English horizontal stock video search queries (2-3 words each) in queries.\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        '  "title": "دلچسپ اردو عنوان",\n'
        '  "story_part1": "پہلا حصہ یہاں",\n'
        '  "tags": ["نبیوں کے واقعات", "Islamic Story Urdu", "Urdu Waqiat", "Storybox"],\n'
        '  "queries": ["ancient desert dunes wide", "sunrise over mountain horizon"]\n'
        "}"
    )

    raw1 = _call_gemini_raw(api_key, prompt_part1, models)
    parsed1 = extract_json(raw1)
    if not parsed1:
        raise RuntimeError("Gemini did not return valid JSON for Prophet story Part 1.")

    part1 = str(parsed1.get("story_part1") or "").strip()
    title = str(parsed1.get("title") or "نبی کا ایک دلچسپ اور ایمان افروز واقعہ").strip()[:95]
    raw_tags = parsed1.get("tags")
    tags = [str(t).strip() for t in raw_tags if str(t).strip()][:15] if isinstance(raw_tags, list) else []
    if not tags:
        tags = ["نبیوں کے واقعات", "Islamic Story Urdu", "Urdu Waqiat", "Storybox"]

    raw_q = parsed1.get("queries")
    queries = [str(q).strip() for q in raw_q if str(q).strip()][:16] if isinstance(raw_q, list) else []
    if len(queries) < 6:
        queries = DEFAULT_SCENE_QUERIES

    prompt_part2 = (
        f"Run #{nonce} Part 2. Continue and COMPLETE the exact same Urdu story to its full dramatic climax, resolution, "
        f"and heartfelt moral lesson.\n"
        f"Story Title: {title}\n"
        f"Part 1 ending context: {part1[-450:]}\n"
        "Strict instructions:\n"
        "- Write ONLY in natural spoken Urdu script (اردو رسم الخط), with zero English or Roman words in story_part2.\n"
        "- Write around 340 to 400 Urdu words for Part 2 so the combined story is ~700+ Urdu words (full 3+ minute voiceover).\n"
        "- Do not use bullet points or markdown inside story_part2; write smooth flowing Urdu prose.\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        '  "story_part2": "دوسرا اور مکمل اختتامی حصہ یہاں"\n'
        "}"
    )

    raw2 = _call_gemini_raw(api_key, prompt_part2, models)
    parsed2 = extract_json(raw2)
    part2 = str((parsed2 or {}).get("story_part2") or "").strip()
    if not part2:
        # Fallback if JSON wasn't wrapped in braces on part 2
        part2 = re.sub(r"```(?:json)?|```", "", raw2).strip()

    full_story = f"{part1} {part2}".strip()
    word_count = len(full_story.split())
    if word_count < 220:
        raise RuntimeError(f"Generated story too short ({word_count} words).")

    print(f"Auto-generated story '{title}' ({word_count} words) on topic: {topic}")
    return title, full_story, tags, queries


async def make_tts_and_boundaries(text: str, mp3_path: Path) -> list[dict]:
    voice = os.getenv("EDGE_TTS_VOICE", "").strip() or "ur-PK-AsadNeural"
    communicate = edge_tts.Communicate(text=text, voice=voice, rate="-6%")
    word_events: list[tuple[float, float, str]] = []

    with open(mp3_path, "wb") as out:
        async for chunk in communicate.stream():
            ctype = chunk.get("type")
            if ctype == "audio":
                out.write(chunk["data"])
            elif ctype in ("WordBoundary", "SentenceBoundary"):
                offset_s = float(chunk.get("offset", 0)) / 10_000_000.0
                dur_s = max(0.08, float(chunk.get("duration", 1_500_000)) / 10_000_000.0)
                piece = str(chunk.get("text") or "").strip()
                if piece:
                    word_events.append((offset_s, offset_s + dur_s, piece))

    phrases: list[dict] = []
    if word_events:
        group_size = 5
        for i in range(0, len(word_events), group_size):
            grp = word_events[i : i + group_size]
            st = round(grp[0][0], 2)
            en = round(max(grp[-1][1], st + 0.6), 2)
            txt = " ".join(w[2] for w in grp).strip()
            if txt and en > st:
                phrases.append({"start": st, "end": en, "text": txt})
    return phrases


def build_fallback_phrases(story_text: str, total_dur: float) -> list[dict]:
    words = [w for w in re.split(r"\s+", story_text.strip()) if w]
    if not words:
        return [{"start": 0.0, "end": total_dur, "text": "مکمل واقعہ"}]
    chunks = [" ".join(words[i : i + 5]) for i in range(0, len(words), 5)]
    step = total_dur / len(chunks)
    out: list[dict] = []
    for idx, ch in enumerate(chunks):
        st = round(idx * step, 2)
        en = round(total_dur if idx == len(chunks) - 1 else (idx + 1) * step, 2)
        if en > st:
            out.append({"start": st, "end": en, "text": ch})
    return out


def format_ass_ts(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def write_ass_captions_and_popups(
    ass_path: Path,
    phrases: list[dict],
    total_dur: float,
) -> None:
    font_family = "Noto Sans"
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caption,{font_family},54,&H00FFFFFF,&H0000FFFF,&H00000000,&H96000000,"
        "-1,0,0,0,102,102,1,0,3,4,2,2,90,90,78,1\n"
        f"Style: SubscribePop,{font_family},38,&H00FFFFFF,&H00FFFFFF,&H00111111,&HE61818D8,"
        "-1,0,0,0,100,100,0,0,3,3,2,9,60,60,70,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    lines: list[str] = []
    for idx, p in enumerate(phrases):
        st = format_ass_ts(p["start"])
        en = format_ass_ts(p["end"])
        accent = CAPTION_ACCENTS[idx % len(CAPTION_ACCENTS)]
        clean_txt = re.sub(r"[{}]", "", p["text"]).strip()
        if not clean_txt:
            continue
        styled = (
            f"{{\\fad(120,120)\\fscx88\\fscy88\\t(0,140,\\fscx104\\fscy104)"
            f"\\t(140,240,\\fscx100\\fscy100)\\1c{accent}}}{clean_txt}"
        )
        lines.append(f"Dialogue: 0,{st},{en},Caption,,0,0,0,,{styled}")

    popup_windows = [(45.0, 51.5), (110.0, 116.5), (162.0, 168.5)]
    for p_start, p_end in popup_windows:
        if p_start + 1.0 < total_dur:
            actual_end = min(p_end, max(p_start + 1.0, total_dur - 0.5))
            st_s = format_ass_ts(p_start)
            en_s = format_ass_ts(actual_end)
            bell_pulse = (
                "{\\fad(180,180)\\move(2150,115,1690,115,0,350)"
                "\\t(450,650,\\frz-12)\\t(650,850,\\frz12)\\t(850,1050,\\frz0)}"
                "🔔  Subscribe & Bell Press Karein"
            )
            lines.append(f"Dialogue: 1,{st_s},{en_s},SubscribePop,,0,0,0,,{bell_pulse}")

    ass_path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def build_clip(query: str, api_key: str, dest: Path, dur: float, idx: int, used_urls: set[str]) -> Path:
    if idx % 2 == 0:
        vf = (
            "scale=2048:1152:force_original_aspect_ratio=increase,"
            "crop=w=1920:h=1080:x='(iw-ow)/2+((iw-ow)*0.45)*sin(t*0.4)':y='(ih-oh)/2',"
            "eq=contrast=1.08:saturation=1.12,fps=30,format=yuv420p"
        )
    else:
        vf = (
            "scale=2048:1152:force_original_aspect_ratio=increase,"
            "crop=w=1920:h=1080:x='(iw-ow)/2':y='(ih-oh)/2+((ih-oh)*0.45)*cos(t*0.4)',"
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
                                ],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                            if res.returncode == 0 and dest.exists() and dest.stat().st_size > 20_000:
                                return dest
        except Exception as e:
            print(f"Clip {idx} ({query}) fallback: {e}")

    make_color_clip(dest, dur, idx)
    return dest


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
            f"lowpass=f=260,volume=0.045,afade=t=in:st=0:d=2.0,afade=t=out:st={fade_out_at:.2f}:d=2.5",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(bg_wav),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if mix_res.returncode == 0 and mixed_wav.exists() and mixed_wav.stat().st_size > 10_000:
            return mixed_wav
    return voice_wav


def main() -> None:
    work = Path("build_long_assets")
    work.mkdir(exist_ok=True)

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()

    title, story_text, tags, queries = auto_generate_prophet_story(gemini_key)

    mp3 = work / "voice.mp3"
    wav = work / "voice.wav"
    phrases = asyncio.run(make_tts_and_boundaries(story_text, mp3))

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3), "-ar", "44100", "-ac", "1", str(wav)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    actual_voice_dur = get_dur(wav)
    if actual_voice_dur < MIN_STORY_SEC:
        raise RuntimeError(
            f"Generated story voice is only {actual_voice_dur:.1f}s (< {MIN_STORY_SEC:.0f}s). "
            "Story length needs to be longer so narration itself is 3+ minutes."
        )

    if not phrases:
        phrases = build_fallback_phrases(story_text, actual_voice_dur)

    print(f"Exact story narration duration: {actual_voice_dur:.1f}s | Caption lines: {len(phrases)}")

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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    ass_file = work / "captions_and_popups.ass"
    write_ass_captions_and_popups(ass_file, phrases, actual_voice_dur)

    styled_video = work / "styled_video.mp4"
    sub_res = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(merged),
            "-vf",
            f"ass={ass_file.name}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            str(styled_video),
        ],
        cwd=str(work),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    video_source = styled_video if (sub_res.returncode == 0 and styled_video.exists() and styled_video.stat().st_size > 20_000) else merged

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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(clips[0]), "-vframes", "1", str(OUTPUT_THUMBNAIL)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    meta = {
        "title": title,
        "description": story_text + "\n\n#Storybox #IslamicStory #UrduWaqiat #IslamicReminder",
        "tags": tags,
        "thumbnail_path": str(OUTPUT_THUMBNAIL),
        "video_path": str(OUTPUT_VIDEO),
    }
    OUTPUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    HISTORY_FILE.write_text(json.dumps({"last_title": title}, ensure_ascii=False), encoding="utf-8")
    print(f"Generated 1920x1080 {OUTPUT_VIDEO} ({get_dur(OUTPUT_VIDEO):.1f}s) with captions & pop-ups.")


if __name__ == "__main__":
    main()
