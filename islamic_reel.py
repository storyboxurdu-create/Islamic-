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
TARGET_CLIPS = 1

AKHRI_ZAMANA_TOPICS = [
    "Aakhri zamana mein fitnon ke waqt imaan aur sabr bachane ka sabaq",
    "Rishton, amanat aur zuban ki hifazat ka aakhri zamana mein paigham",
    "Aakhri zamana mein waqt ki tezi aur ghafil na hone ka sabaq",
    "Aakhri zamana mein ilm uthne aur sachai par qaim rehne ka sabaq",
    "Aakhri zamana ki aazmaishon mein tawakkul aur istighfar ki ahmiyat",
    "Aakhri zamana mein namaz aur zikr se dil ko mazboot rakhne ka paigham",
]

SPACE_QUERIES = [
    "outer space stars",
    "galaxy nebula space",
    "planet earth space",
    "moon stars night",
]

HUMAN_VOICES = [
    "ur-PK-AsadNeural",
    "ur-PK-UzmaNeural",
]

TEXT_COLORS = [
    "0x0F172A",
    "0x0B3B60",
    "0x14532D",
    "0x7C2D12",
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
        "generationConfig": {"temperature": 0.9},
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
    raise RuntimeError(f"Gemini Short generation failed: {last_err}")


def _clean_title(raw_title: str, fallback_topic: str) -> str:
    cleaned = re.sub(r"[“”\"'`#]+", "", (raw_title or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:،۔")
    if not cleaned or "daily reminder" in cleaned.lower():
        return fallback_topic[:95].strip()
    return cleaned[:95].strip()


def generate_short_story(api_key: str) -> dict:
    key = (api_key or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required.")

    models = _list_models(key)
    topic = random.choice(AKHRI_ZAMANA_TOPICS)
    nonce = random.randint(100000, 999999)

    prompt = (
        f"Run #{nonce}.\n"
        f"Write a ~40-50 second Urdu YouTube Short/Reel story on:\n"
        f"Topic: {topic}\n\n"
        "Rules:\n"
        "- 'title' MUST represent the whole Short in natural Urdu script (اردو رسم الخط).\n"
        "- Do NOT write 'Daily reminder' or any date in 'title'.\n"
        "- Write ~115-135 natural spoken Urdu words in 'narration' with clear beginning, middle, and ending lesson.\n"
        "- Write ONLY natural spoken Urdu prose, no bullets or markdown.\n"
        "- Provide 1 primary English space query in 'query' (e.g. 'outer space stars').\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        '  "title": "مکمل اردو عنوان",\n'
        '  "narration": "مکمل اردو بیان",\n'
        '  "tags": ["آخری زمانہ", "Aakhri Zamana", "Islamic Shorts", "Urdu Bayan"],\n'
        '  "query": "outer space stars"\n'
        "}"
    )

    raw = _call_gemini(key, prompt, models)
    parsed = _extract_json(raw)
    if not parsed:
        raise RuntimeError("Gemini did not return valid JSON.")

    narration = re.sub(r"\s+", " ", str(parsed.get("narration") or "").strip())
    if len(narration.split()) < 60:
        raise RuntimeError("Generated narration is too short.")

    title = _clean_title(str(parsed.get("title") or ""), topic)

    raw_tags = parsed.get("tags")
    tags = [str(t).strip() for t in raw_tags if str(t).strip()][:15] if isinstance(raw_tags, list) else []
    if not tags:
        tags = ["آخری زمانہ", "Aakhri Zamana", "Islamic Shorts", "Urdu Bayan"]

    primary_q = str(parsed.get("query") or "").strip()
    queries = [primary_q] + [q for q in SPACE_QUERIES if q != primary_q] if primary_q else list(SPACE_QUERIES)

    print(f"Short Title: {title}")
    return {
        "id": f"short_{nonce}",
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
    spaced = re.sub(r"([۔.!?؟،,])\s*", r"\1 ", text.strip())
    await edge_tts.Communicate(text=spaced, voice=voice).save(str(mp3_path))


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


def build_single_space_frame(queries: list[str], api_key: str, dest: Path, dur: float, work: Path) -> Path:
    canvas_bg = "0xF4F6F9"
    card_w, card_h = 960, 540
    card_x, card_y = (1080 - card_w) // 2, (1920 - card_h) // 2

    if api_key:
        for term in queries:
            url = (
                f"https://pixabay.com/api/videos/?key={urllib.parse.quote(api_key)}"
                f"&q={urllib.parse.quote(term)}&per_page=8&safesearch=true"
            )
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for hit in data.get("hits", []):
                    vids = hit.get("videos", {})
                    for k in ("medium", "large", "small", "tiny"):
                        link = (vids.get(k) or {}).get("url")
                        if link:
                            raw = work / "single_space.raw.mp4"
                            dl_req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"})
                            with urllib.request.urlopen(dl_req, timeout=25) as dresp, open(raw, "wb") as out:
                                out.write(dresp.read())
                            if raw.exists() and raw.stat().st_size > 30_000:
                                fc = (
                                    f"color=c={canvas_bg}:s=1080x1920:r=24[bg];"
                                    f"[1:v]scale={card_w}:{card_h}:force_original_aspect_ratio=increase,"
                                    f"crop={card_w}:{card_h},setsar=1[fg];"
                                    f"[bg][fg]overlay={card_x}:{card_y}:shortest=1,format=yuv420p[outv]"
                                )
                                res = subprocess.run(
                                    [
                                        "ffmpeg",
                                        "-y",
                                        "-t",
                                        f"{dur:.2f}",
                                        "-f",
                                        "lavfi",
                                        "-i",
                                        f"color=c={canvas_bg}:s=1080x1920:r=24:d={dur:.2f}",
                                        "-stream_loop",
                                        "-1",
                                        "-i",
                                        str(raw),
                                        "-filter_complex",
                                        fc,
                                        "-map",
                                        "[outv]",
                                        "-t",
                                        f"{dur:.2f}",
                                        "-an",
                                        "-c:v",
                                        "libx264",
                                        "-preset",
                                        "ultrafast",
                                        "-crf",
                                        "25",
                                        "-pix_fmt",
                                        "yuv420p",
                                        str(dest),
                                    ]
                                )
                                if res.returncode == 0 and dest.exists() and dest.stat().st_size > 20_000:
                                    return dest
            except Exception as e:
                print(f"Single space video ({term}) note: {e}")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={canvas_bg}:s=1080x1920:r=24:d={dur:.2f}",
            "-vf",
            f"drawbox=x={card_x}:y={card_y}:w={card_w}:h={card_h}:color=0x070B19:t=fill,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "25",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ],
        check=True,
    )
    return dest


def apply_frame_captions(
    input_video: Path,
    output_video: Path,
    header_title: str,
    segments: list[dict],
    font_path: Path,
    total_dur: float,
    work: Path,
) -> Path:
    font_str = str(font_path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")
    top_label = escape_ff_text(header_title[:42])
    filter_parts: list[str] = [
        f"drawtext=fontfile='{font_str}':text='{top_label}':"
        f"fontcolor=0x0F172A:fontsize=46:x=(w-tw)/2:y=360"
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
        filter_parts.append(
            f"drawtext=fontfile='{font_str}':text='{txt_esc}':"
            f"fontcolor={col}:fontsize=62:x=(w-tw)/2:y=1320:"
            f"enable='between(t,{st:.2f},{en:.2f})'"
        )

    script_file = work / "frame_vf_chain.txt"
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
            "ultrafast",
            "-crf",
            "25",
            "-pix_fmt",
            "yuv420p",
            str(output_video),
        ]
    )
    if res.returncode != 0 or not output_video.exists() or output_video.stat().st_size < 20_000:
        print(f"Frame overlay fallback (rc={res.returncode}), using base video.")
        return input_video
    return output_video


def main() -> None:
    work = Path("build_short_assets")
    work.mkdir(exist_ok=True)

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()
    font_path = ensure_font(work)

    story = generate_short_story(gemini_key)
    title = story["title"]
    narration = story["narration"]
    tags = story["tags"]
    queries = story["queries"]

    mp3 = work / "short_voice.mp3"
    asyncio.run(save_human_voice(narration, mp3))
    dur = get_dur(mp3)

    segments = build_segments(narration, dur)
    base_frame = build_single_space_frame(queries, pixabay_key, work / "space_frame.mp4", dur, work)

    styled = work / "short_styled.mp4"
    v_src = apply_frame_captions(base_frame, styled, title, segments, font_path, dur, work)

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
    print(f"Generated single-space framed short {OUTPUT_VIDEO} ({get_dur(OUTPUT_VIDEO):.1f}s) with title: {title}")


if __name__ == "__main__":
    main()
