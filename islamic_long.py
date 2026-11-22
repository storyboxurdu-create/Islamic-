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

MIN_STORY_SEC = 185.0  # ~3m 05s
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


def auto_generate_prophet_story(api_key: str) -> tuple[str, str, list[str], list[str]]:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing in environment/secrets.")

    topic = random.choice(PROPHET_TOPICS)
    nonce = random.randint(10000, 99999)

    prompt = (
        f"Run #{nonce}. Auto-generate a complete, deeply engaging, and dramatic Urdu story about an interesting "
        f"episode from the life of a Prophet ({topic}).\n"
        "Strict instructions:\n"
        "- Write ONLY in natural spoken Urdu script (اردو رسم الخط), with zero English or Roman words in story_text or title.\n"
        "- Make it a full, continuous ~3.3-minute narration: around 460 to 540 Urdu words, with a complete beginning, rising tension, turning point, resolution, and final moral ending.\n"
        "- Do not use bullet points or markdown inside story_text; write smooth flowing Urdu prose ready for voiceover.\n"
        "- Also provide 12 short English horizontal stock video search queries (2-3 words each) in queries matching the scenes of the story.\n"
        "Return ONLY valid JSON in this exact structure:\n"
        "{\n"
        '  "title": "دلچسپ اردو عنوان",\n'
        '  "story_text": "مکمل طویل اردو کہانی یہاں",\n'
        '  "tags": ["نبیوں کے واقعات", "Islamic Story Urdu", "Urdu Waqiat", "Storybox"],\n'
        '  "queries": ["ancient desert dunes wide", "sunrise over mountain horizon"]\n'
        "}"
    )

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.95},
    }

    enc_key = urllib.parse.quote(api_key)
    models = list_gemini_models(api_key) or [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest",
        "gemini-1.5-flash",
    ]

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
            with urllib.request.urlopen(req, timeout=50) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                break
        except Exception as e:
            last_err = e

    if not payload:
        raise RuntimeError(f"Gemini request failed: {last_err}")

    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    raw_out = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    parsed = extract_json(raw_out)
    if not parsed:
        raise RuntimeError("Gemini did not return valid JSON for Prophet story.")

    story_text = str(parsed.get("story_text") or "").strip()
    title = str(parsed.get("title") or "نبی کا ایک دلچسپ اور ایمان افروز واقعہ").strip()[:95]
    raw_tags = parsed.get("tags")
    tags = [str(t).strip() for t in raw_tags if str(t).strip()][:15] if isinstance(raw_tags, list) else []
    if not tags:
        tags = ["نبیوں کے واقعات", "Islamic Story Urdu", "Urdu Waqiat", "Storybox"]

    raw_q = parsed.get("queries")
    queries = [str(q).strip() for q in raw_q if str(q).strip()][:16] if isinstance(raw_q, list) else []
    if len(queries) < 6:
        queries = DEFAULT_SCENE_QUERIES

    if len(story_text.split()) < 150:
        raise RuntimeError("Generated story is too short for 3+ minute long video.")

    print(f"Auto-generated story '{title}' ({len(story_text.split())} words) on topic: {topic}")
    return title, story_text, tags, queries


async def make_tts(text: str, mp3_path: Path) -> None:
    voice = os.getenv("EDGE_TTS_VOICE", "").strip() or "ur-PK-AsadNeural"
    await edge_tts.Communicate(text=text, voice=voice, rate="-4%").save(str(mp3_path))


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
                for k in ("medium", "large", "small", "tiny"):
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
                                    "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30",
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


def main() -> None:
    work = Path("build_long_assets")
    work.mkdir(exist_ok=True)

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()

    title, story_text, tags, queries = auto_generate_prophet_story(gemini_key)

    mp3 = work / "voice.mp3"
    wav = work / "voice.wav"
    asyncio.run(make_tts(story_text, mp3))
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
            "Increase story length so narration itself reaches 3+ minutes without padding."
        )

    print(f"Exact story narration duration: {actual_voice_dur:.1f}s")

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

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(merged),
            "-i",
            str(wav),
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
    print(f"Generated 1920x1080 {OUTPUT_VIDEO} ({get_dur(OUTPUT_VIDEO):.1f}s) matching story end.")


if __name__ == "__main__":
    main()
