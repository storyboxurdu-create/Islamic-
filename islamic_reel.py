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
        "id": "story_01_bilal_aur_waqt",
        "title": "Aakhri Zamana Ka Qissa: Jab Waqt Hath Se Nikal Gaya | Islamic Short",
        "scenes": [
            {
                "text": "Aakhri zamane mein sab se bada dhoka yeh hai ke insaan samajhta hai uske paas abhi bohat waqt hai.",
                "query": "hourglass sand time close up",
            },
            {
                "text": "Bilal aik kamyab freelancer tha jo din raat phone aur laptop par masroof rehta tha.",
                "query": "man working laptop night desk",
            },
            {
                "text": "Namaz aaye to kehta, bas yeh kaam poora kar loon, phir parh loonga.",
                "query": "clock ticking evening light",
            },
            {
                "text": "Rishtedar ya walidain baat karte to woh kaan mein earbuds laga kar aage barh jata.",
                "query": "person wearing headphones walking",
            },
            {
                "text": "Ek din uske qareebi dost ka achanak inteqal ho gaya, aur bilal ka dil sunn reh gaya.",
                "query": "rainy window dark mood",
            },
            {
                "text": "Janaze mein kharay ho kar usne pehli baar mehsoos kiya ke dolat aur screens wahan saath nahi jaate.",
                "query": "cemetery trees peaceful morning",
            },
            {
                "text": "Us raat bilal ghar aaya, wuzu kiya, aur ro ro kar pichli kotahiyon ki maafi mangi.",
                "query": "water splashing hands wuzu",
            },
            {
                "text": "Usne samajh liya ke aakhri zamane ke fitnon se bachne ka pehla qadam apne waqt ko Allah ke hawale karna hai.",
                "query": "mosque courtyard peaceful light",
            },
            {
                "text": "Aaj ki practical tip yeh hai: har namaz se das minute pehle apna kaam aur mobile side par rakh dein.",
                "query": "smartphone placed on table",
            },
            {
                "text": "Namaz ke baad sirf teen minute khamoshi se baith kar apni aakhirat aur niyyat ka jaiza lein.",
                "query": "person sitting quietly reflection",
            },
            {
                "text": "Jab aap waqt ka haq ada karte hain, to Allah aapke dil mein barakat aur sukoon daal deta hai.",
                "query": "sunrise rays over horizon",
            },
            {
                "text": "Aaj ka yeh chhota sa badlao kal aapki nijaat ka zariya ban sakta hai.",
                "query": "green leaves sunlight nature",
            },
        ],
    },
    {
        "id": "story_02_ayesha_aur_zuban",
        "title": "Aakhri Zamana Mein Aik Lafz Ka Asar | Islamic Short",
        "scenes": [
            {
                "text": "Aakhri zamane mein aksar log baray gunahon se nahi, balkay be-ehtiyati ki baaton se phisalte hain.",
                "query": "crowd walking city street",
            },
            {
                "text": "Ayesha ko aik group mein kisi ke khilaf suni sunayi baat mili aur usne bina soche aage bhej di.",
                "query": "typing message phone screen",
            },
            {
                "text": "Woh baat aage se aage phailti gayi aur aik be-qusoor insaan ki izzat aur rishtay toot gaye.",
                "query": "broken glass shadow dark",
            },
            {
                "text": "Jab ayesha ko haqeeqat ka pata chala to usay bohat pachtawa hua ke uski ungliyon se kitna nuqsan ho gaya.",
                "query": "woman regret evening light",
            },
            {
                "text": "Usne khud aage barh kar sach wazeh kiya aur jis ka dil dukha tha us se maafi mangi.",
                "query": "two people talking calm",
            },
            {
                "text": "Aakhri zamane mein zuban aur forward button dono aik badi aazmaish hain.",
                "query": "spark ember dark background",
            },
            {
                "text": "Jo baat yaqeen aur adab ke baghair aage barhayi jaye, woh dil aur ghar dono ko kamzor karti hai.",
                "query": "foggy road trees morning",
            },
            {
                "text": "Is ki practical tip yeh hai: koi bhi baat ya post forward karne se pehle khud se do sawal poochein.",
                "query": "open book wooden table",
            },
            {
                "text": "Pehla sawal: kya yeh sach hai? Aur doosra sawal: kya is se kisi ka dil to nahi dukhega?",
                "query": "calm lake reflection sunset",
            },
            {
                "text": "Agar jawab haan aur na mein ho, tab hi aage barhayein, warna khamoshi ikhtiyar kar lein.",
                "query": "quiet mountain peak clouds",
            },
            {
                "text": "Zuban ki hifazat insaan ko fitnon se bachati hai aur dil ko naram rakhti hai.",
                "query": "lantern light warm night",
            },
            {
                "text": "Apni baat aur kirdar ko aaj hi sanwar lein.",
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
    HISTORY_FILE.write_text(json.dumps(used_ids[-100:], indent=2), encoding="utf-8")


def _extract_json_object(raw_text: str) -> dict | None:
    cleaned = re.sub(r"```(?:json)?|```", "", raw_text).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def generate_story_with_gemini(api_key: str, used_ids: list[str]) -> dict | None:
    if not api_key:
        return None

    recent_list = ", ".join(used_ids[-15:]) if used_ids else "none"
    prompt = (
        "You are an Islamic storytelling scriptwriter for 35-40 second vertical YouTube Shorts in clear, natural Roman Urdu. "
        "Write ONE rich, emotional, and creative 'Aakhri Zamana' (End Times) story with a named character, a clear turning point, and a practical daily tip at the end. "
        "Do NOT write dry generic slogans or disconnected lines; every scene must flow smoothly like a gripping story. "
        f"Avoid these previous topic IDs/themes: {recent_list}. "
        "Output ONLY a valid JSON object (no markdown, no extra text) with this exact structure:\n"
        "{\n"
        '  "id": "unique_short_snake_case_id",\n'
        '  "title": "Compelling Story Title | Islamic Short",\n'
        '  "scenes": [\n'
        '    {"text": "Clear natural Roman Urdu sentence (10-16 words)", "query": "3-4 English stock video keywords matching this exact moment"}\n'
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Include 12 scenes total so total narration is around 125-150 words (~35-42 seconds).\n"
        "- Scene 1: Strong hook about Aakhri Zamana.\n"
        "- Scenes 2-7: A vivid, relatable story about a character facing a modern/end-times test and realizing the truth.\n"
        "- Scenes 8-11: Clear, actionable practical tip step-by-step.\n"
        "- Scene 12: Memorable closing reminder.\n"
        "- Use simple, easy-to-pronounce Roman Urdu words (avoid awkward abbreviations or overly complex words)."
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
                valid_scenes.append({
                    "text": str(s["text"]).strip(),
                    "query": str(s["query"]).strip(),
                })
        if len(valid_scenes) < 10:
            return None
        story_id = str(parsed.get("id") or f"story_{random.randint(10000, 99999)}")
        title = str(parsed.get("title") or "Aakhri Zamana Ka Qissa | Islamic Short")
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


async def generate_voice_segment(text: str, mp3_path: Path) -> None:
    communicate = edge_tts.Communicate(
        text=text,
        voice="ur-PK-AsadNeural",
        rate="-8%",
        pitch="-2Hz",
    )
    await communicate.save(str(mp3_path))


def normalize_audio_segment(raw_mp3: Path, clean_wav: Path) -> float:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_mp3),
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=11,apad=pad_dur=0.25",
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
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _wrap_caption_lines(text: str, max_chars: int = 34) -> list[str]:
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
        "drawbox=x=0:y=ih*0.66:w=iw:h=ih*0.24:color=black@0.42:t=fill"
    ]

    for seg in caption_segments:
        start = round(seg["start"], 2)
        end = round(seg["end"], 2)
        lines = _wrap_caption_lines(seg["text"], max_chars=32)
        if not lines:
            continue

        line_height = 66
        total_h = len(lines) * line_height
        base_y = int(1920 * 0.75) - (total_h // 2)

        for idx, line in enumerate(lines):
            safe_line = _escape_drawtext(line)
            y_pos = base_y + idx * line_height
            draw_cmd = (
                f"drawtext=text='{safe_line}'{font_arg}:"
                f"fontsize=48:fontcolor=white:"
                f"borderw=4:bordercolor=black@0.9:"
                f"shadowx=0:shadowy=3:shadowcolor=black@0.75:"
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

    # Generate clean, normalized voice per scene so every clip & caption syncs with the exact spoken sentence
    voice_segments: list[Path] = []
    scene_durations: list[float] = []
    for idx, scene in enumerate(scenes):
        raw_mp3 = work_dir / f"voice_{idx:02d}.mp3"
        clean_wav = work_dir / f"voice_{idx:02d}.wav"
        asyncio.run(generate_voice_segment(scene["text"], raw_mp3))
        seg_dur = normalize_audio_segment(raw_mp3, clean_wav)
        seg_dur = max(2.4, round(seg_dur, 2))
        voice_segments.append(clean_wav)
        scene_durations.append(seg_dur)

    audio_list = work_dir / "audio.txt"
    with open(audio_list, "w", encoding="utf-8") as f:
        for wav in voice_segments:
            f.write(f"file '{wav.resolve()}'\n")

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
            str(audio_list),
            "-c:a",
            "pcm_s16le",
            str(full_voice_wav),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    total_voice_dur = get_media_duration(full_voice_wav)
    target_duration = max(32.0, round(total_voice_dur, 2))
    if target_duration > total_voice_dur and scene_durations:
        scene_durations[-1] = round(scene_durations[-1] + (target_duration - total_voice_dur), 2)

    used_urls: set[str] = set()
    normalized_clips: list[Path] = []
    caption_segments: list[dict] = []
    cursor_time = 0.0

    for idx, (scene, scene_dur) in enumerate(zip(scenes, scene_durations)):
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
            "160k",
            "-shortest",
            str(OUTPUT_VIDEO),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    final_dur = get_media_duration(OUTPUT_VIDEO)
    full_narration = " ".join(s["text"] for s in scenes)
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
    print(f"Generated {OUTPUT_VIDEO} ({final_dur:.1f}s) with {len(normalized_clips)} clips & synced voice/captions.")


if __name__ == "__main__":
    main()
