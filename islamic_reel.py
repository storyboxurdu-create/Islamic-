import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
import edge_tts
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1920
FPS = 30
AUDIO_RATE = 44100

QUESTIONS_PER_VIDEO = 5
PAUSE_SEC = 0.35
USE_VOICE = True
URDU_VOICE = "ur-PK-AsadNeural"
VOICE_RATE = "+8%"

HISTORY_FILE = "islamic_history.json"
FINAL_SHORT_FILE = Path("final_islamic_short.mp4")
OUTPUT_DIR = Path("output_reels")
WORK_DIR = Path("work_frames")


def get_urdu_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoNastaliqUrdu-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]
    for word in words[1:]:
        test_line = f"{current} {word}"
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test_line
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def draw_centered_text(draw: ImageDraw.ImageDraw, text: str, center_x: int, top_y: int, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = center_x - (w // 2) - bbox[0]
    y = top_y - bbox[1]
    draw.text((x, y), text, font=font, fill=fill)
    return h


def load_history_state(history_path: str) -> dict:
    path = Path(history_path)
    if not path.exists():
        state = {"run_count": 0, "seen_questions": [], "history": []}
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return {
            "run_count": int(data.get("run_count", 0)),
            "seen_questions": list(data.get("seen_questions", [])),
            "history": list(data.get("history", [])),
        }
    return {"run_count": 0, "seen_questions": [], "history": []}


def save_history_state(history_path: str, state: dict):
    Path(history_path).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_json_array(raw_text: str) -> list[dict]:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if not match:
        raise ValueError("No JSON array found in model output")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise ValueError("Parsed output is not a list")
    return parsed


def _normalize_q(q: str) -> str:
    return re.sub(r"\s+", " ", q).strip().lower()


def generate_qa_via_gemini(count: int, seen_questions: list[str], run_num: int) -> list[dict]:
    import urllib.request

    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY set nahi hai; unique sawal generate karne ke liye key zaroori hai.")

    avoid_sample = " | ".join(seen_questions[-80:])
    prompt = (
        f"Generate exactly {count} completely new, unique, accurate, and demanding Islamic quiz "
        "question-and-answer items in Urdu for a YouTube Short (Tafseer, Quranic precision, "
        "Seerat, Fiqh rulings, and Hadith terminology—avoid common beginner questions).\n"
        f"Batch number: {run_num}.\n"
        f"Do NOT repeat or rephrase any of these questions: {avoid_sample if avoid_sample else 'none'}.\n"
        "Return ONLY a valid JSON array with objects having exact keys: "
        '"question", "answer", "spoken_q", "spoken_a".\n'
        "Keep question and answer concise so they fit cleanly on a mobile screen."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9},
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    candidates = body.get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text_out = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    raw_items = _extract_json_array(text_out)

    seen_norm = {_normalize_q(sq) for sq in seen_questions}
    batch_norm = set()
    valid_items = []

    for obj in raw_items:
        if not isinstance(obj, dict):
            continue
        q = str(obj.get("question") or "").strip()
        a = str(obj.get("answer") or "").strip()
        if not q or not a:
            continue
        q_norm = _normalize_q(q)
        if q_norm in seen_norm or q_norm in batch_norm:
            continue
        batch_norm.add(q_norm)
        sq = str(obj.get("spoken_q") or f"سوال: {q}").strip()
        sa = str(obj.get("spoken_a") or f"جواب: {a}").strip()
        valid_items.append({
            "question": q,
            "answer": a,
            "spoken_q": sq,
            "spoken_a": sa,
        })

    if len(valid_items) < count:
        raise ValueError(f"Expected {count} unique items, got {len(valid_items)}")
    return valid_items[:count]


def generate_unique_batch(count: int, state: dict) -> list[dict]:
    run_num = state["run_count"] + 1
    seen_questions = state["seen_questions"]

    items = generate_qa_via_gemini(count, seen_questions, run_num)
    if len(items) != count:
        raise RuntimeError("Muntakhab unique sawalat mukammal nahi ho sakay.")
    return items


async def generate_tts(text: str, out_mp3: Path):
    communicate = edge_tts.Communicate(text=text, voice=URDU_VOICE, rate=VOICE_RATE)
    await communicate.save(str(out_mp3))


def get_media_duration(media_path: Path) -> float:
    if not media_path.exists() or media_path.stat().st_size == 0:
        return 1.2
    res = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        val = float(res.stdout.strip())
        return max(1.0, val)
    except ValueError:
        return 1.2


def make_slide(
    top_heading: str,
    badge_label: str,
    badge_color: tuple[int, int, int],
    main_text: str,
    out_path: Path,
    header_font,
    badge_font,
    body_font,
):
    img = Image.new("RGB", (WIDTH, HEIGHT), (10, 31, 38))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, WIDTH, 210], fill=(16, 185, 129))
    draw.rectangle([0, 210, WIDTH, 224], fill=(245, 158, 11))
    draw_centered_text(draw, top_heading, WIDTH // 2, 55, header_font, (255, 255, 255))

    draw.rectangle([0, HEIGHT - 150, WIDTH, HEIGHT], fill=(15, 118, 110))
    draw.rectangle([0, HEIGHT - 162, WIDTH, HEIGHT - 150], fill=(245, 158, 11))
    draw_centered_text(draw, "الحمد للہ", WIDTH // 2, HEIGHT - 115, header_font, (254, 243, 199))

    card_left = 44
    card_right = WIDTH - 44
    card_top = 275
    card_bottom = HEIGHT - 215
    draw.rounded_rectangle(
        [card_left, card_top, card_right, card_bottom],
        radius=36,
        fill=(255, 251, 235),
        outline=(217, 119, 6),
        width=10,
    )

    badge_w = 420
    badge_h = 120
    bx1 = (WIDTH - badge_w) // 2
    by1 = card_top + 45
    draw.rounded_rectangle(
        [bx1, by1, bx1 + badge_w, by1 + badge_h],
        radius=28,
        fill=badge_color,
        outline=(255, 255, 255),
        width=4,
    )
    draw_centered_text(draw, badge_label, WIDTH // 2, by1 + 22, badge_font, (255, 255, 255))

    max_text_w = (card_right - card_left) - 110
    lines = wrap_text(draw, main_text, body_font, max_text_w)

    measured = []
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=body_font)
        lh = (bb[3] - bb[1]) + 34
        measured.append((line, lh))

    total_h = sum(lh for _, lh in measured)
    text_area_top = by1 + badge_h + 75
    text_area_bottom = card_bottom - 55
    cur_y = text_area_top + max(0, ((text_area_bottom - text_area_top) - total_h) // 2)

    for line, lh in measured:
        draw_centered_text(draw, line, WIDTH // 2, cur_y, body_font, (17, 24, 39))
        cur_y += lh

    img.save(out_path, format="PNG")


def build_segment_with_audio(
    img_path: Path,
    audio_path: Path,
    duration_sec: float,
    out_mp4: Path,
):
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img_path),
            "-i", str(audio_path),
            "-filter_complex",
            f"[1:a]aformat=sample_fmts=fltp:sample_rates={AUDIO_RATE}:channel_layouts=stereo,apad=pad_dur=0.1[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-t", f"{duration_sec:.2f}",
            "-r", str(FPS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", str(AUDIO_RATE), "-ac", "2", "-b:a", "128k",
            str(out_mp4),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def build_silent_segment(
    img_path: Path,
    duration_sec: float,
    out_mp4: Path,
    darken: bool = False,
):
    vf = "eq=brightness=-0.05" if darken else "null"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img_path),
            "-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo",
            "-t", f"{duration_sec:.2f}",
            "-r", str(FPS),
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", str(AUDIO_RATE), "-ac", "2", "-b:a", "128k",
            "-shortest",
            str(out_mp4),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def render_multi_qa_video(batch_items: list[dict], run_num: int, header_font, badge_font, body_font) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch_work = WORK_DIR / f"run_{run_num:03d}"
    if batch_work.exists():
        shutil.rmtree(batch_work)
    batch_work.mkdir(parents=True, exist_ok=True)

    all_clips = []

    for q_num, item in enumerate(batch_items, start=1):
        question = item["question"].strip()
        answer = item["answer"].strip()
        spoken_q = (item.get("spoken_q") or f"سوال: {question}").strip()
        spoken_a = (item.get("spoken_a") or f"جواب: {answer}").strip()

        q_img = batch_work / f"q_{q_num}.png"
        a_img = batch_work / f"a_{q_num}.png"

        make_slide(
            "بسم اللہ الرحمن الرحیم",
            f"سوال {q_num}",
            (217, 119, 6),
            question,
            q_img,
            header_font,
            badge_font,
            body_font,
        )
        make_slide(
            "بسم اللہ الرحمن الرحیم",
            f"جواب {q_num}",
            (5, 150, 105),
            answer,
            a_img,
            header_font,
            badge_font,
            body_font,
        )

        q_clip = batch_work / f"q_{q_num}.mp4"
        p_clip = batch_work / f"p_{q_num}.mp4"
        a_clip = batch_work / f"a_{q_num}.mp4"

        if USE_VOICE:
            q_tts = batch_work / f"q_{q_num}_voice.mp3"
            a_tts = batch_work / f"a_{q_num}_voice.mp3"
            asyncio.run(generate_tts(spoken_q, q_tts))
            asyncio.run(generate_tts(spoken_a, a_tts))
            q_dur = get_media_duration(q_tts) + 0.1
            a_dur = get_media_duration(a_tts) + 0.15
            build_segment_with_audio(q_img, q_tts, q_dur, q_clip)
            build_segment_with_audio(a_img, a_tts, a_dur, a_clip)
        else:
            build_silent_segment(q_img, 2.5, q_clip, darken=False)
            build_silent_segment(a_img, 2.5, a_clip, darken=False)

        build_silent_segment(q_img, PAUSE_SEC, p_clip, darken=True)
        all_clips.extend([q_clip, p_clip, a_clip])

    concat_list = batch_work / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{clip.resolve()}'\n" for clip in all_clips),
        encoding="utf-8",
    )

    archived_mp4 = OUTPUT_DIR / f"islamic_run_{run_num:03d}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", str(AUDIO_RATE), "-ac", "2", "-b:a", "128k",
            "-movflags", "+faststart",
            str(archived_mp4),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    shutil.copyfile(archived_mp4, FINAL_SHORT_FILE)
    return FINAL_SHORT_FILE


def main():
    state = load_history_state(HISTORY_FILE)
    batch_items = generate_unique_batch(QUESTIONS_PER_VIDEO, state)
    run_num = state["run_count"] + 1

    header_font = get_urdu_font(44)
    badge_font = get_urdu_font(48)
    body_font = get_urdu_font(62)

    created = render_multi_qa_video(batch_items, run_num, header_font, badge_font, body_font)

    state["run_count"] = run_num
    state["seen_questions"].extend(it["question"] for it in batch_items)
    state["history"].append({
        "run_no": run_num,
        "items": batch_items,
    })
    save_history_state(HISTORY_FILE, state)

    print(f"Generated run {run_num} with {len(batch_items)} unique Q&A items: {created}")


if __name__ == "__main__":
    main()
