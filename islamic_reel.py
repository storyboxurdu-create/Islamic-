import asyncio
import json
import os
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
PAUSE_SEC = 0.8
URDU_VOICE = "ur-PK-AsadNeural"
VOICE_RATE = "+10%"

HISTORY_FILE = "islamic_history.json"
FINAL_SHORT_FILE = Path("final_islamic_short.mp4")
OUTPUT_DIR = Path("output_reels")
WORK_DIR = Path("work_frames")

DEFAULT_ITEMS = [
    {"id": 1, "question": "نماز میں کتنی بار خارش کرنے سے نماز ٹوٹ جاتی ہے؟", "answer": "تین بار۔"},
    {"id": 2, "question": "قرآن مجید کی سب سے طویل سورۃ کون سی ہے؟", "answer": "سورۃ البقرۃ۔"},
    {"id": 3, "question": "قرآن مجید کی سب سے مختصر سورۃ کون سی ہے؟", "answer": "سورۃ الکوثر۔"},
    {"id": 4, "question": "قرآن مجید میں کل کتنی سورتیں ہیں؟", "answer": "114 سورتیں۔"},
    {"id": 5, "question": "قرآن مجید میں کل کتنے پارے ہیں؟", "answer": "30 پارے۔"},
    {"id": 6, "question": "اسلام کے کل کتنے ارکان ہیں؟", "answer": "پانچ ارکان۔"},
    {"id": 7, "question": "دن میں فرض نمازوں کی تعداد کتنی ہے؟", "answer": "پانچ نمازیں۔"},
    {"id": 8, "question": "سب سے پہلے کون سی وحی نازل ہوئی؟", "answer": "سورۃ العلق کی ابتدائی آیات۔"},
    {"id": 9, "question": "نبی کریم صلی اللہ علیہ وسلم پر قرآن مجید کتنے عرصے میں نازل ہوا؟", "answer": "تئیس سال میں۔"},
    {"id": 10, "question": "ہجرتِ مدینہ کے وقت نبی کریم صلی اللہ علیہ وسلم کے ہمراہ کون تھے؟", "answer": "حضرت ابوبکر صدیق رضی اللہ عنہ۔"},
    {"id": 11, "question": "غزوہ بدر کس ہجری میں پیش آیا؟", "answer": "دو ہجری میں۔"},
    {"id": 12, "question": "قرآن مجید میں کس نبی کا ذکر سب سے زیادہ بار آیا ہے؟", "answer": "حضرت موسیٰ علیہ السلام۔"},
    {"id": 13, "question": "وضو کے کتنے فرائض ہیں؟", "answer": "چار فرائض۔"},
    {"id": 14, "question": "غسل کے کتنے فرائض ہیں؟", "answer": "تین فرائض۔"},
    {"id": 15, "question": "اسلام کے پہلے خلیفہ کون تھے؟", "answer": "حضرت ابوبکر صدیق رضی اللہ عنہ۔"},
    {"id": 16, "question": "مسجدِ نبوی کس شہر میں واقع ہے؟", "answer": "مدینہ منورہ میں۔"},
    {"id": 17, "question": "شبِ معراج کس مہینے میں پیش آئی؟", "answer": "رجب المرجب میں۔"},
    {"id": 18, "question": "زکوٰۃ کس سن ہجری میں فرض ہوئی؟", "answer": "دو ہجری میں۔"},
    {"id": 19, "question": "خاتم النبیین کسے کہا جاتا ہے؟", "answer": "حضرت محمد صلی اللہ علیہ وسلم کو۔"},
    {"id": 20, "question": "قرآن مجید کی کس سورۃ میں بسم اللہ دو بار آئی ہے؟", "answer": "سورۃ النمل میں۔"},
]


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
        state = {"next_index": 0, "batch_no": 0, "items": DEFAULT_ITEMS}
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        items = data
        next_idx = 0
        batch_no = 0
    elif isinstance(data, dict):
        items = data.get("items", [])
        next_idx = int(data.get("next_index", 0))
        batch_no = int(data.get("batch_no", 0))
    else:
        items = []
        next_idx = 0
        batch_no = 0

    if len(items) < 20:
        existing_questions = {x.get("question") for x in items}
        for item in DEFAULT_ITEMS:
            if item["question"] not in existing_questions:
                items.append(item)
            if len(items) >= 20:
                break

    state = {"next_index": next_idx, "batch_no": batch_no, "items": items}
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def save_history_state(history_path: str, state: dict):
    Path(history_path).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


async def generate_tts(text: str, out_mp3: Path):
    communicate = edge_tts.Communicate(text=text, voice=URDU_VOICE, rate=VOICE_RATE)
    await communicate.save(str(out_mp3))


def get_media_duration(media_path: Path) -> float:
    if not media_path.exists() or media_path.stat().st_size == 0:
        return 1.5
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
        return max(1.2, val)
    except ValueError:
        return 1.5


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
    # Rich dark emerald-navy background with colorful top bar & card
    img = Image.new("RGB", (WIDTH, HEIGHT), (10, 31, 38))
    draw = ImageDraw.Draw(img)

    # Top colorful banner
    draw.rectangle([0, 0, WIDTH, 210], fill=(16, 185, 129))
    draw.rectangle([0, 210, WIDTH, 224], fill=(245, 158, 11))
    draw_centered_text(draw, top_heading, WIDTH // 2, 55, header_font, (255, 255, 255))

    # Bottom colorful bar
    draw.rectangle([0, HEIGHT - 150, WIDTH, HEIGHT], fill=(15, 118, 110))
    draw.rectangle([0, HEIGHT - 162, WIDTH, HEIGHT - 150], fill=(245, 158, 11))
    draw_centered_text(draw, "الحمد للہ", WIDTH // 2, HEIGHT - 115, header_font, (254, 243, 199))

    # Main colorful card
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

    # Wide badge so text never clips on left/right
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

    # Body text inside card
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
            f"[1:a]aformat=sample_fmts=fltp:sample_rates={AUDIO_RATE}:channel_layouts=stereo,apad=pad_dur=0.2[aout]",
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


def build_silent_pause(img_path: Path, duration_sec: float, out_mp4: Path):
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img_path),
            "-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo",
            "-t", f"{duration_sec:.2f}",
            "-r", str(FPS),
            "-vf", "eq=brightness=-0.05",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", str(AUDIO_RATE), "-ac", "2", "-b:a", "128k",
            "-shortest",
            str(out_mp4),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def render_multi_qa_video(batch_items: list[dict], batch_num: int, header_font, badge_font, body_font) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch_work = WORK_DIR / f"batch_{batch_num:03d}"
    if batch_work.exists():
        shutil.rmtree(batch_work)
    batch_work.mkdir(parents=True, exist_ok=True)

    all_clips = []

    for q_num, item in enumerate(batch_items, start=1):
        question = item["question"].strip()
        answer = item["answer"].strip()

        q_img = batch_work / f"q_{q_num}.png"
        a_img = batch_work / f"a_{q_num}.png"
        q_tts = batch_work / f"q_{q_num}_voice.mp3"
        a_tts = batch_work / f"a_{q_num}_voice.mp3"

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

        spoken_q = f"سوال نمبر {q_num}: {question}"
        spoken_a = f"جواب: {answer}"
        asyncio.run(generate_tts(spoken_q, q_tts))
        asyncio.run(generate_tts(spoken_a, a_tts))

        q_dur = get_media_duration(q_tts) + 0.25
        a_dur = get_media_duration(a_tts) + 0.35

        q_clip = batch_work / f"q_{q_num}.mp4"
        p_clip = batch_work / f"p_{q_num}.mp4"
        a_clip = batch_work / f"a_{q_num}.mp4"

        build_segment_with_audio(q_img, q_tts, q_dur, q_clip)
        build_silent_pause(q_img, PAUSE_SEC, p_clip)
        build_segment_with_audio(a_img, a_tts, a_dur, a_clip)

        all_clips.extend([q_clip, p_clip, a_clip])

    concat_list = batch_work / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{clip.resolve()}'\n" for clip in all_clips),
        encoding="utf-8",
    )

    archived_mp4 = OUTPUT_DIR / f"islamic_batch_{batch_num:03d}.mp4"
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
    items = state["items"]
    if not items:
        print("No quiz items found.")
        return

    total = len(items)
    start_idx = state["next_index"] % total
    count = min(QUESTIONS_PER_VIDEO, total)

    batch_items = [items[(start_idx + i) % total] for i in range(count)]
    batch_num = state["batch_no"] + 1

    header_font = get_urdu_font(44)
    badge_font = get_urdu_font(48)
    body_font = get_urdu_font(62)

    created = render_multi_qa_video(batch_items, batch_num, header_font, badge_font, body_font)

    state["next_index"] = (start_idx + count) % total
    state["batch_no"] = batch_num
    save_history_state(HISTORY_FILE, state)

    print(f"Generated batch {batch_num} with {count} Q&A items: {created}")


if __name__ == "__main__":
    main()
