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
from islamic_short_story import generate_fresh_short_story

OUTPUT_VIDEO = Path("final_islamic_short.mp4")
OUTPUT_META = Path("short_meta.json")
TARGET_CLIPS = 12
MIN_SHORT_SEC = 32.0

TEXT_COLORS = [
    "0xFFD60A",  # Bold Gold
    "0x4ADE80",  # Bright Green
    "0x38BDF8",  # Bright Sky Blue
    "0xFB923C",  # Bold Orange
    "0xFFFFFF",  # Pure White
]

FONT_URLS = [
    "https://github.com/google/fonts/raw/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf",
    "https://github.com/google/fonts/raw/main/ofl/notonastaliqurdu/NotoNastaliqUrdu%5Bwght%5D.ttf",
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


async def make_tts_and_chunks(text: str, mp3_path: Path) -> list[tuple[float, str]]:
    voice = os.getenv("EDGE_TTS_VOICE", "").strip() or "ur-PK-AsadNeural"
    communicate = edge_tts.Communicate(text=text, voice=voice, rate="-4%")
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
        chunks = [" ".join(words[i : i + 3]) for i in range(0, len(words), 3)] or ["مکمل کہانی"]
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
    if idx % 2 == 0:
        vf = (
            "scale=1188:2112:force_original_aspect_ratio=increase,"
            "crop=w=1080:h=1920:x='(iw-ow)/2+((iw-ow)*0.45)*sin(t*0.45)':y='(ih-oh)/2',"
            "eq=contrast=1.08:saturation=1.14,fps=30,format=yuv420p"
        )
    else:
        vf = (
            "scale=1188:2112:force_original_aspect_ratio=increase,"
            "crop=w=1080:h=1920:x='(iw-ow)/2':y='(ih-oh)/2+((ih-oh)*0.45)*cos(t*0.45)',"
            "eq=contrast=1.08:saturation=1.14,fps=30,format=yuv420p"
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

    # Subscribe + Bell pop-up once around middle of the Short
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

    story = generate_fresh_short_story(gemini_key)
    title = story["title"]
    narration = story["narration"]
    tags = story["tags"]
    queries = story["queries"]

    mp3 = work / "short_voice.mp3"
    wav = work / "short_voice.wav"
    grouped = asyncio.run(make_tts_and_chunks(narration, mp3))

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3), "-ar", "44100", "-ac", "1", str(wav)],
        check=True,
    )

    dur = get_dur(wav)
    if dur < MIN_SHORT_SEC:
        pad = round(MIN_SHORT_SEC - dur + 0.5, 2)
        pw = work / "short_voice_pad.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav), "-af", f"apad=pad_dur={pad}", "-ar", "44100", "-ac", "1", str(pw)],
            check=True,
        )
        pw.replace(wav)
        dur = get_dur(wav)

    segments = build_sequential_segments(grouped, narration, dur)
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
    )

    if not OUTPUT_VIDEO.exists() or OUTPUT_VIDEO.stat().st_size == 0:
        raise RuntimeError("Failed to generate final_islamic_short.mp4")

    meta = {
        "title": title,
        "description": narration + "\n\n#Storybox #IslamicShorts #UrduWaqiat #IslamicReminder",
        "tags": tags,
        "video_path": str(OUTPUT_VIDEO.resolve()),
    }
    OUTPUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {OUTPUT_VIDEO} ({get_dur(OUTPUT_VIDEO):.1f}s) with title: {title}")


if __name__ == "__main__":
    main()
