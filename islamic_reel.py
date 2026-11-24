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

OUTPUT_VIDEO = Path("final_islamic_short.mp4")
OUTPUT_META = Path("short_meta.json")
TARGET_CLIPS = 12
MIN_SHORT_SEC = 32.0

AKHRI_ZAMANA_TOPICS = [
    "Aakhri zamana mein fitnon ke waqt imaan aur sabr bachane ka sabaq",
    "Dajjal ke fitne se bachne ke liye ahadith mein aayi rehnumai aur dua",
    "Aakhri zamana mein waqt ki tezi aur ghafil na hone ka paigham",
    "Aakhri zamana mein ilm uthne aur sachai par qaim rehne ka sabaq",
    "Aakhri zamana ki aazmaishon mein tawakkul aur istighfar ki ahmiyat",
    "Aakhri zamana mein rishton, amanat aur zuban ki hifazat ka sabaq",
    "Aakhri zamana mein namaz aur zikr se dil ko mazboot rakhne ka paigham",
    "Aakhri zamana ke halaat mein hidayat aur sachi tawbah ka waqia o sabaq",
]

HUMAN_VOICES = [
    "ur-PK-AsadNeural",
    "ur-PK-UzmaNeural",
]

TEXT_COLORS = [
    "0xFFD60A",
    "0x4ADE80",
    "0x38BDF8",
    "0xFB923C",
    "0xFFFFFF",
]

FONT_URLS = [
    "https://github.com/google/fonts/raw/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf",
    "https://github.com/google/fonts/raw/main/ofl/notonastaliqurdu/NotoNastaliqUrdu%5Bwght%5D.ttf",
]


def _extract_json(raw: str) -> dict | None:
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _list_models(api_key: str) -> list[str]:
    enc_key = urllib.parse.quote(api_key)
    for base in (
        f"https://generativelanguage.googleapis.com/v1beta/models?key={enc_key}",
        f"https://generativelanguage.googleapis.com/v1/models?key={enc_key}",
    ):
        try:
            req = urllib.request.Request(base, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            out: list[str] = []
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods") or []
                name = str(m.get("name") or "")
                if not name or (methods and "generateContent" not in methods):
                    continue
                mid = name.split("/")[-1]
                if "gemini" in mid and "embedding" not in mid and "imagen" not in mid and "veo" not in mid:
                    if mid not in out:
                        out.append(mid)
            if out:
                return out
        except Exception:
            pass
    return ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest", "gemini-1.5-flash"]


def _call_gemini(api_key: str, prompt: str, models: list[str]) -> str:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 1.0},
    }
    enc_key = urllib.parse.quote(api_key)
    urls: list[str] = []
    for mid in models:
        urls.append(f"https://generativelanguage.googleapis.com/v1beta/models/{mid}:generateContent?key={enc_key}")
        urls.append(f"https://generativelanguage.googleapis.com/v1/models/{mid}:generateContent?key={enc_key}")

    last_err = None
    for u in urls:
        try:
            req = urllib.request.Request(
                u,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            txt = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
            if txt:
                return txt
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Gemini Aakhri Zamana Short failed: {last_err}")


def _clean_title(raw_title: str, fallback_topic: str) -> str:
    cleaned = re.sub(r"[“”\"'`#]+", "", (raw_title or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:،۔")
    if not cleaned or "daily reminder" in cleaned.lower():
        return fallback_topic[:95].strip()
    return cleaned[:95].strip()


def generate_akhri_zamana_short(api_key: str) -> dict:
    key = (api_key or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required.")

    models = _list_models(key)
    topic = random.choice(AKHRI_ZAMANA_TOPICS)
    nonce = random.randint(100000, 999999)

    prompt = (
        f"Run #{nonce}.\n"
        f"Write a complete ~40-50 second Urdu YouTube Short/Reel script strictly about Aakhri Zamana (end times in Islam):\n"
        f"Focus: {topic}\n\n"
        "Rules:\n"
        "- 'title' MUST capture the whole Aakhri Zamana message/short in natural Urdu script (اردو رسم الخط).\n"
        "- Do NOT write 'Daily reminder' or any date in 'title'.\n"
        "- Write ~115-135 natural spoken Urdu words in 'narration' with calm, human storytelling tone, clear flow, and an impactful ending lesson.\n"
        "- Write ONLY in natural spoken Urdu script, smooth voiceover prose, no bullets or markdown.\n"
        "- Provide 4 short 2-3 word English stock video queries in 'queries' matching Aakhri Zamana / reflection / night / sky / light.\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        '  "title": "آخری زمانے سے متعلق مکمل اردو عنوان",\n'
        '  "narration": "آخری زمانے پر مکمل اور پرسکون اردو بیان",\n'
        '  "tags": ["آخری زمانہ", "Aakhri Zamana", "Islamic Shorts", "Urdu Bayan"],\n'
        '  "queries": ["dark storm sky", "glowing lantern night", "starry desert horizon", "open quran book"]\n'
        "}"
    )

    raw = _call_gemini(key, prompt, models)
    parsed = _extract_json(raw)
    if not parsed:
        raise RuntimeError("Gemini did not return valid JSON for Aakhri Zamana Short.")

    narration = re.sub(r"\s+", " ", str(parsed.get("narration") or "").strip())
    if len(narration.split()) < 60:
        raise RuntimeError("Generated Aakhri Zamana narration is too short.")

    title = _clean_title(str(parsed.get("title") or ""), topic)

    raw_tags = parsed.get("tags")
    tags = [str(t).strip() for t in raw_tags if str(t).strip()][:15] if isinstance(raw_tags, list) else []
    if not tags:
        tags = ["آخری زمانہ", "Aakhri Zamana", "Islamic Shorts", "Urdu Bayan"]

    raw_q = parsed.get("queries")
    queries = [str(q).strip() for q in raw_q if str(q).strip()][:8] if isinstance(raw_q, list) else []
    if not queries:
        queries = ["dark storm sky", "glowing lantern night", "starry desert horizon", "open quran book"]

    print(f"Aakhri Zamana Short Title: {title}")
    return {
        "id": f"akhri_short_{nonce}",
        "title": title,
        "narration": narration,
        "tags": tags,
        "queries": queries,
    }


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
    dest = font_dir / "UrduShortFont.ttf"
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


async def save_human_voice(text: str, mp3_path: Path) -> None:
    env_voice = os.getenv("EDGE_TTS_VOICE", "").strip()
    voice = env_voice if env_voice else random.choice(HUMAN_VOICES)
    print(f"Using voice: {voice}")
    # Punctuation pauses help Edge-TTS sound calm and natural like human speech
    spaced = re.sub(r"([۔.!?؟،,])\s*", r"\1 ", text.strip())
    await edge_tts.Communicate(text=spaced, voice=voice, rate="-2%").save(str(mp3_path))


def build_segments(story_text: str, total_dur: float) -> list[dict]:
    words = [w for w in re.split(r"\s+", story_text.strip()) if w]
    if not words:
        return [{"start": 0.0, "end": total_dur, "text": "آخری زمانہ"}]
    chunks = [" ".join(words[i : i + 3]) for i in range(0, len(words), 3)]
    step = total_dur / len(chunks)
    segments: list[dict] = []
    for idx, ch in enumerate(chunks):
        st = round(idx * step, 2)
        en = round(total_dur if idx == len(chunks) - 1 else (idx + 1) * step, 2)
        if en > st + 0.05:
            segments.append({"start": st, "end": en, "text": ch})
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
            f"color=c={color}:s=1080x1920:d={dur:.2f}",
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


def build_short_clip(query: str, api_key: str, dest: Path, dur: float, idx: int, used_urls: set[str]) -> Path:
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,eq=contrast=1.06:saturation=1.1,fps=30,format=yuv420p"
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
            print(f"Short clip {idx} ({query}) fallback: {e}")

    make_color_clip(dest, dur, idx)
    return dest


def apply_short_overlays(
    input_video: Path,
    output_video: Path,
    segments: list[dict],
    font_path: Path,
    total_dur: float,
    work: Path,
) -> Path:
    font_str = str(font_path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")
    filter_parts: list[str] = [
        "drawbox=x=0:y=ih-340:w=iw:h=240:color=black@0.72:t=fill"
    ]

    for idx, seg in enumerate(segments):
        st = max(0.0, float(seg["start"]))
        en = min(total_dur, float(seg["end"]))
        if en <= st:
            continue
        col = TEXT_COLORS[idx % len(TEXT_COLORS)]
        txt_esc = escape_ff_text(seg["text"])
        if not txt_esc:
            continue
        dur_s = max(0.1, en - st)
        x_expr = f"max(60\\, min(w-tw-60\\, (w-tw)/2 + 45*sin(((t-{st:.2f})/{dur_s:.2f})*3.14159)))"
        y_expr = "h-255"
        filter_parts.append(
            f"drawtext=fontfile='{font_str}':text='{txt_esc}':"
            f"fontcolor={col}:fontsize=68:borderw=5:bordercolor=black@0.95:"
            f"shadowcolor=black@0.85:shadowx=3:shadowy=3:"
            f"x={x_expr}:y={y_expr}:enable='between(t,{st:.2f},{en:.2f})'"
        )

    p_start = round(min(14.0, total_dur * 0.42), 2)
    p_end = round(min(total_dur - 0.5, p_start + 5.0), 2)
    if p_end > p_start + 1.0:
        box_w, box_h = 680, 96
        bell_txt = escape_ff_text("🔔 SUBSCRIBE & BELL")
        x_box = f"if(lt(t-{p_start:.2f},0.35), w - ((t-{p_start:.2f})/0.35)*({box_w}+180), (w-{box_w})/2 + 10*sin((t-{p_start:.2f})*7))"
        y_box = "150"
        filter_parts.append(
            f"drawbox=x='{x_box}':y='{y_box}':w={box_w}:h={box_h}:"
            f"color=0xDC2626@0.95:t=fill:enable='between(t,{p_start:.2f},{p_end:.2f})'"
        )
        filter_parts.append(
            f"drawtext=fontfile='{font_str}':text='{bell_txt}':"
            f"fontcolor=0xFDE047:fontsize=44:borderw=4:bordercolor=black@0.95:"
            f"x='({x_box})+38':y='({y_box})+22':enable='between(t,{p_start:.2f},{p_end:.2f})'"
        )

    script_file = work / "short_vf_chain.txt"
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
        print(f"Short overlay fallback (rc={res.returncode}), using merged video.")
        return input_video
    return output_video


def main() -> None:
    work = Path("build_short_assets")
    work.mkdir(exist_ok=True)

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()
    font_path = ensure_font(work)

    story = generate_akhri_zamana_short(gemini_key)
    title = story["title"]
    narration = story["narration"]
    tags = story["tags"]
    queries = story["queries"]

    mp3 = work / "short_voice.mp3"
    asyncio.run(save_human_voice(narration, mp3))
    dur = get_dur(mp3)

    segments = build_segments(narration, dur)
    each_dur = round(dur / TARGET_CLIPS, 2)
    used_urls: set[str] = set()
    clips: list[Path] = []

    for i in range(TARGET_CLIPS):
        q = queries[i % len(queries)]
        clips.append(build_short_clip(q, pixabay_key, work / f"sclip_{i:02d}.mp4", each_dur, i, used_urls))

    concat_txt = work / "short_concat.txt"
    concat_txt.write_text("\n".join(f"file '{c.resolve()}'" for c in clips), encoding="utf-8")

    merged = work / "short_merged.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c:v", "copy", str(merged)],
        check=True,
    )

    styled = work / "short_styled.mp4"
    v_src = apply_short_overlays(merged, styled, segments, font_path, dur, work)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(v_src),
            "-i",
            str(mp3),
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

    if not OUTPUT_VIDEO.exists() or OUTPUT_VIDEO.stat().st_size == 0:
        raise RuntimeError("Failed to generate final_islamic_short.mp4")

    meta = {
        "title": title,
        "description": narration + "\n\n#آخری_زمانہ #AakhriZamana #IslamicShorts #UrduBayan",
        "tags": tags,
        "video_path": str(OUTPUT_VIDEO.resolve()),
    }
    OUTPUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {OUTPUT_VIDEO} ({get_dur(OUTPUT_VIDEO):.1f}s) with title: {title}")


if __name__ == "__main__":
    main()
