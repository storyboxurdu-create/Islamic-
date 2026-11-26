import json
import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1920
FPS = 30

QUESTION_SEC = 4
PAUSE_SEC = 2
ANSWER_SEC = 4

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
    {"id": 9, "question": "نبی کریم صلی اللہ علیہ وسلم پر قرآن مجید کتنے عرصے میں نازل ہوا؟", "answer": "تئیس (23) سال میں۔"},
    {"id": 10, "question": "ہجرتِ مدینہ کے وقت نبی کریم صلی اللہ علیہ وسلم کے ہمراہ کون تھے؟", "answer": "حضرت ابوبکر صدیق رضی اللہ عنہ۔"},
    {"id": 11, "question": "غزوہ بدر کس ہجری میں پیش آیا؟", "answer": "2 ہجری میں۔"},
    {"id": 12, "question": "قرآن مجید میں کس نبی کا ذکر سب سے زیادہ بار آیا ہے؟", "answer": "حضرت موسیٰ علیہ السلام۔"},
    {"id": 13, "question": "وضو کے کتنے فرائض ہیں؟", "answer": "چار فرائض۔"},
    {"id": 14, "question": "غسل کے کتنے فرائض ہیں؟", "answer": "تین فرائض۔"},
    {"id": 15, "question": "اسلام کے پہلے خلیفہ کون تھے؟", "answer": "حضرت ابوبکر صدیق رضی اللہ عنہ۔"},
    {"id": 16, "question": "مسجدِ نبوی کس شہر میں واقع ہے؟", "answer": "مدینہ منورہ میں۔"},
    {"id": 17, "question": "شبِ معراج کس مہینے میں پیش آئی؟", "answer": "رجب المرجب میں۔"},
    {"id": 18, "question": "زکوٰۃ کس سن ہجری میں فرض ہوئی؟", "answer": "2 ہجری میں۔"},
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


def load_or_create_items(history_path: str) -> list[dict]:
    path = Path(history_path)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_ITEMS, ensure_ascii=False, indent=2), encoding="utf-8")
        return DEFAULT_ITEMS

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        items = data.get("items", [])
    elif isinstance(data, list):
        items = data
    else:
        items = []

    if len(items) < 20:
        existing_questions = {x.get("question") for x in items}
        for item in DEFAULT_ITEMS:
            if item["question"] not in existing_questions:
                items.append(item)
            if len(items) >= 20:
                break
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    return items


def make_slide(
    stage_label: str,
    stage_color: tuple[int, int, int],
    main_text: str,
    out_path: Path,
    title_font,
    body_font,
):
    img = Image.new("RGB", (WIDTH, HEIGHT), (15, 23, 42))
    draw = ImageDraw.Draw(img)

    margin = 48
    draw.rectangle(
        [margin, margin + 260, WIDTH - margin, HEIGHT - margin - 260],
        fill=(248, 250, 252),
        outline=(22, 163, 74),
        width=14,
    )

    badge_w, badge_h = 260, 92
    bx1 = (WIDTH - badge_w) // 2
    by1 = margin + 310
    draw.rounded_rectangle(
        [bx1, by1, bx1 + badge_w, by1 + badge_h],
        radius=20,
        fill=stage_color,
    )
    tb = draw.textbbox((0, 0), stage_label, font=title_font)
    tx = bx1 + (badge_w - (tb[2] - tb[0])) // 2
    ty = by1 + (badge_h - (tb[3] - tb[1])) // 2 - 6
    draw.text((tx, ty), stage_label, font=title_font, fill=(255, 255, 255))

    max_text_w = WIDTH - (margin * 2) - 120
    lines = wrap_text(draw, main_text, body_font, max_text_w)

    line_heights = []
    for line in lines:
        lb = draw.textbbox((0, 0), line, font=body_font)
        line_heights.append(max(64, (lb[3] - lb[1]) + 28))

    total_h = sum(line_heights)
    card_top = by1 + badge_h + 60
    card_bottom = HEIGHT - margin - 300
    cur_y = card_top + max(0, ((card_bottom - card_top) - total_h) // 2)

    for line, lh in zip(lines, line_heights):
        lb = draw.textbbox((0, 0), line, font=body_font)
        lw = lb[2] - lb[0]
        lx = (WIDTH - lw) // 2
        draw.text((lx, cur_y), line, font=body_font, fill=(17, 24, 39))
        cur_y += lh

    img.save(out_path, format="PNG")


def render_reel(item: dict, idx: int, title_font, body_font) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    item_work = WORK_DIR / f"reel_{idx:03d}"
    if item_work.exists():
        shutil.rmtree(item_work)
    item_work.mkdir(parents=True, exist_ok=True)

    question = item["question"].strip()
    answer = item["answer"].strip()

    q_img = item_work / "q.png"
    a_img = item_work / "a.png"

    make_slide("سوال", (234, 88, 12), question, q_img, title_font, body_font)
    make_slide("جواب", (22, 163, 74), answer, a_img, title_font, body_font)

    q_clip = item_work / "q.mp4"
    p_clip = item_work / "p.mp4"
    a_clip = item_work / "a.mp4"
    concat_list = item_work / "concat.txt"
    archived_mp4 = OUTPUT_DIR / f"islamic_reel_{idx:03d}.mp4"

    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(q_img),
            "-t", str(QUESTION_SEC), "-r", str(FPS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(q_clip),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(q_img),
            "-t", str(PAUSE_SEC), "-r", str(FPS),
            "-vf", "eq=brightness=-0.08",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p_clip),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(a_img),
            "-t", str(ANSWER_SEC), "-r", str(FPS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(a_clip),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    concat_list.write_text(
        f"file '{q_clip.resolve()}'\n"
        f"file '{p_clip.resolve()}'\n"
        f"file '{a_clip.resolve()}'\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(archived_mp4),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    shutil.copyfile(archived_mp4, FINAL_SHORT_FILE)
    return FINAL_SHORT_FILE


def main():
    items = load_or_create_items(HISTORY_FILE)
    if not items:
        print("No quiz items found.")
        return

    title_font = get_urdu_font(54)
    body_font = get_urdu_font(68)

    for idx, item in enumerate(items, start=1):
        out_file = OUTPUT_DIR / f"islamic_reel_{idx:03d}.mp4"
        if not out_file.exists():
            created = render_reel(item, idx, title_font, body_font)
            print(f"Generated: {created} (archived as {out_file})")
            break
    else:
        last_idx = len(items)
        last_item = items[-1]
        created = render_reel(last_item, last_idx, title_font, body_font)
        print(f"All items already rendered; refreshed {created}")


if __name__ == "__main__":
    main()
