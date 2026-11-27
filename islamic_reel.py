import asyncio
import json
import math
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
VOICE_RATE = "+4%"
CURTAIN_OPEN_SEC = 0.45

HISTORY_FILE = "islamic_history.json"
FINAL_SHORT_FILE = Path("final_islamic_short.mp4")
OUTPUT_DIR = Path("output_reels")
WORK_DIR = Path("work_frames")

UNIQUE_QA_BANK = [
    (
        "قرآن مجید کی کس سورہ کی ہر آیت میں لفظ اللہ آیا ہے؟",
        "In which Surah of the Quran does the word Allah appear in every verse?",
        "سورہ المجادلہ۔",
        "Surah Al-Mujadila.",
        "سوال: قرآن مجید کی کس سورہ کی ہر آیت میں لفظ اللہ آیا ہے؟",
        "جواب: سورہ المجادلہ۔",
    ),
    (
        "صلح حدیبیہ کس ہجری میں واقع ہوئی؟",
        "In which Hijri year did the Treaty of Hudaybiyyah take place?",
        "چھ ہجری میں۔",
        "In 6 AH.",
        "سوال: صلح حدیبیہ کس ہجری میں واقع ہوئی؟",
        "جواب: چھ ہجری میں۔",
    ),
    (
        "اصطلاح حدیث میں متواتر روایت کسے کہتے ہیں؟",
        "In Hadith terminology, what is a Mutawatir narration?",
        "جسے ہر دور میں اتنی کثیر جماعت نے روایت کیا ہو کہ جھوٹ پر اتفاق محال ہو۔",
        "A narration transmitted at every stage by so many narrators that a lie is inconceivable.",
        "سوال: اصطلاح حدیث میں متواتر روایت کسے کہتے ہیں؟",
        "جواب: جسے ہر دور میں اتنی کثیر جماعت نے بیان کیا ہو کہ جھوٹ پر اتفاق ممکن نہ ہو۔",
    ),
    (
        "قرآن مجید میں کس صحابی کا نام صراحتا آیا ہے؟",
        "Which Companion's name is explicitly mentioned in the Quran?",
        "حضرت زید بن حارثہ رضی اللہ عنہ۔",
        "Zayd ibn Harithah (may Allah be pleased with him).",
        "سوال: قرآن مجید میں کس صحابی کا نام واضح طور پر آیا ہے؟",
        "جواب: حضرت زید بن حارثہ رضی اللہ عنہ۔",
    ),
    (
        "نزول قرآن کے اعتبار سے سب سے پہلی مکمل سورہ کون سی ہے؟",
        "Which Surah was revealed complete first in chronological order?",
        "سورہ الفاتحہ۔",
        "Surah Al-Fatihah.",
        "سوال: نزول قرآن کے اعتبار سے سب سے پہلی مکمل سورہ کون سی ہے؟",
        "جواب: سورہ الفاتحہ۔",
    ),
    (
        "قرآن مجید کی کس سورہ میں دو سجدہ تلاوت ہیں؟",
        "Which Surah of the Quran contains two verses of prostration?",
        "سورہ الحج میں۔",
        "In Surah Al-Hajj.",
        "سوال: قرآن مجید کی کس سورہ میں دو سجدہ تلاوت ہیں؟",
        "جواب: سورہ الحج میں۔",
    ),
    (
        "غزوہ تبوک کس سن ہجری میں پیش آیا؟",
        "In which Hijri year did the Expedition of Tabuk take place?",
        "نو ہجری میں۔",
        "In 9 AH.",
        "سوال: غزوہ تبوک کس سن ہجری میں پیش آیا؟",
        "جواب: نو ہجری میں۔",
    ),
    (
        "قرآن مجید میں سب سے طویل آیت کون سی ہے؟",
        "Which is the longest verse in the Quran?",
        "سورہ البقرہ کی آیت نمبر 282۔",
        "Verse 282 of Surah Al-Baqarah.",
        "سوال: قرآن مجید میں سب سے لمبی آیت کون سی ہے؟",
        "جواب: سورہ البقرہ کی آیت نمبر دو سو بیاسی۔",
    ),
    (
        "نماز جنازہ میں کتنی تکبیریں کہی جاتی ہیں؟",
        "How many Takbirs are recited in Salat al-Janazah?",
        "چار تکبیریں۔",
        "Four Takbirs.",
        "سوال: نماز جنازہ میں کتنی تکبیریں کہی جاتی ہیں؟",
        "جواب: چار تکبیریں۔",
    ),
    (
        "صحابہ کرام میں سب سے پہلے کس نے ہجرت حبشہ کی قیادت کی؟",
        "Who led the first migration to Abyssinia among the Companions?",
        "حضرت عثمان بن عفان رضی اللہ عنہ۔",
        "Uthman ibn Affan (may Allah be pleased with him).",
        "سوال: صحابہ کرام میں سب سے پہلے کس نے ہجرت حبشہ کی قیادت کی؟",
        "جواب: حضرت عثمان بن عفان رضی اللہ عنہ نے۔",
    ),
    (
        "قرآن مجید کی کس سورہ میں لفظ رحمن بار بار آیا ہے؟",
        "In which Surah is Ar-Rahman repeated across verses?",
        "سورہ رحمن میں۔",
        "In Surah Ar-Rahman.",
        "سوال: قرآن مجید کی کس سورہ میں لفظ رحمن بار بار آیا ہے؟",
        "جواب: سورہ رحمن میں۔",
    ),
    (
        "حج کے دوران یوم عرفہ کس تاریخ کو ہوتا ہے؟",
        "On which date of Dhul-Hijjah is the Day of Arafah?",
        "نو ذوالحجہ کو۔",
        "On the 9th of Dhul-Hijjah.",
        "سوال: حج کے دوران یوم عرفہ کس تاریخ کو ہوتا ہے؟",
        "جواب: نو ذوالحجہ کو۔",
    ),
    (
        "علم اصول فقہ میں اجماع سے کیا مراد ہے؟",
        "In Usul al-Fiqh, what does Ijma mean?",
        "کسی شرعی مسئلے پر امت کے مجتہدین کا ایک دور میں اتفاق۔",
        "Consensus of the qualified jurists of the Ummah in an era on a ruling.",
        "سوال: علم اصول فقہ میں اجماع سے کیا مراد ہے؟",
        "جواب: کسی شرعی مسئلے پر امت کے مجتہدین کا ایک دور میں اتفاق۔",
    ),
    (
        "قرآن مجید میں کس نبی کا ذکر سب سے زیادہ مرتبہ آیا ہے؟",
        "Which Prophet is mentioned most frequently by name in the Quran?",
        "حضرت موسی علیہ السلام۔",
        "Prophet Musa (peace be upon him).",
        "سوال: قرآن مجید میں کس نبی کا ذکر سب سے زیادہ بار آیا ہے؟",
        "جواب: حضرت موسی علیہ السلام کا۔",
    ),
    (
        "فتح مکہ کس سن ہجری میں ہوئی؟",
        "In which Hijri year did the Conquest of Makkah occur?",
        "آٹھ ہجری میں۔",
        "In 8 AH.",
        "سوال: فتح مکہ کس سن ہجری میں ہوئی؟",
        "جواب: آٹھ ہجری میں۔",
    ),
]


def safe_display_text(text: str) -> str:
    """Remove invisible/format characters that render as missing-glyph boxes in Pillow."""
    cleaned = re.sub(r"[\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]", "", text)
    cleaned = cleaned.replace("صراحتاً", "صراحتا").replace("اً", "ا")
    return re.sub(r"\s+", " ", cleaned).strip()


def to_spoken_urdu(text: str) -> str:
    cleaned = safe_display_text(text)
    cleaned = re.sub(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]", "", cleaned)
    replacements = {
        "سورۃ": "سورہ",
        "زکوٰۃ": "زکوۃ",
        "صلوٰۃ": "نماز",
        "حٰمٓ": "حا میم",
        "یٰس": "یاسین",
        "الرحمٰن": "الرحمان",
        "ؤ": "و",
        "ئ": "ی",
        "ى": "ی",
        "ۃ": "ہ",
    }
    for src, dst in replacements.items():
        cleaned = cleaned.replace(src, dst)
    return re.sub(r"\s+", " ", cleaned).strip()


def _has_glyph(font, ch: str) -> bool:
    if ch.isspace():
        return True
    try:
        mask = font.getmask(ch)
        return mask.size[0] > 0 and mask.size[1] > 0
    except Exception:
        return True


def sanitize_for_font(text: str, font) -> str:
    """Drop characters that have no glyph in the chosen font so boxes never appear."""
    out = []
    for ch in text:
        if _has_glyph(font, ch):
            out.append(ch)
    return "".join(out).strip()


def get_urdu_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def get_latin_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    clean_txt = sanitize_for_font(safe_display_text(text), font)
    words = clean_txt.split()
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
    safe_txt = sanitize_for_font(safe_display_text(text), font)
    if not safe_txt:
        return 0
    bbox = draw.textbbox((0, 0), safe_txt, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = center_x - (w // 2) - bbox[0]
    y = top_y - bbox[1]
    draw.text((x, y), safe_txt, font=font, fill=fill)
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


def generate_unique_batch(count: int, state: dict) -> list[dict]:
    seen = set(state["seen_questions"])
    fresh = []

    cycle = 0
    while len(fresh) < count:
        for ur_q, en_q, ur_a, en_a, sp_q, sp_a in UNIQUE_QA_BANK:
            q_text = safe_display_text(ur_q if cycle == 0 else f"{ur_q} ({cycle + 1})")
            if q_text in seen:
                continue
            fresh.append({
                "question": q_text,
                "question_en": safe_display_text(en_q),
                "answer": safe_display_text(ur_a),
                "answer_en": safe_display_text(en_a),
                "spoken_q": to_spoken_urdu(sp_q),
                "spoken_a": to_spoken_urdu(sp_a),
            })
            seen.add(q_text)
            if len(fresh) == count:
                break
        cycle += 1

    return fresh


async def generate_tts(text: str, out_mp3: Path):
    spoken_clean = to_spoken_urdu(text)
    communicate = edge_tts.Communicate(text=spoken_clean, voice=URDU_VOICE, rate=VOICE_RATE)
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


def draw_islamic_set_background(draw: ImageDraw.ImageDraw, t_sec: float, darken: bool = False):
    """Draw a unique Islamic arch & hanging lantern set in the scene background."""
    wall_col = (10, 27, 34) if darken else (13, 36, 45)
    arch_col = (18, 48, 58) if darken else (22, 60, 72)
    gold_col = (165, 112, 18) if darken else (217, 155, 38)

    draw.rectangle([0, 224, WIDTH, HEIGHT - 162], fill=wall_col)

    # Decorative Islamic arch niche on left set area
    draw.rounded_rectangle([24, 270, 245, HEIGHT - 235], radius=105, fill=arch_col, outline=gold_col, width=4)

    # Hanging lantern (qandeel) with subtle gentle sway
    sway = int(4 * math.sin(t_sec * 2.0))
    lx = 135 + sway
    ly = 335
    draw.line([(135, 224), (lx, ly)], fill=gold_col, width=4)
    draw.polygon([(lx - 18, ly + 16), (lx + 18, ly + 16), (lx + 24, ly + 52), (lx - 24, ly + 52)], fill=(245, 190, 66) if not darken else (175, 130, 35), outline=gold_col)
    draw.polygon([(lx - 24, ly + 52), (lx + 24, ly + 52), (lx, ly + 74)], fill=gold_col)

    # Small book stand (rehal) near bottom of left set
    rx = 135
    ry = HEIGHT - 255
    draw.polygon([(rx - 38, ry), (rx + 38, ry), (rx + 26, ry - 22), (rx - 26, ry - 22)], fill=(120, 72, 28))
    draw.rounded_rectangle([rx - 30, ry - 44, rx + 30, ry - 20], radius=6, fill=(245, 240, 220), outline=gold_col, width=2)


def draw_molvi_kurta_shalwar_topi(
    draw: ImageDraw.ImageDraw,
    base_x: int,
    base_y: int,
    t_sec: float,
):
    """Draw a calm, dignified Molvi wearing Kurta, Shalwar, and Topi (skullcap)."""
    breath_y = int(2 * math.sin(t_sec * 2.4))
    bx = base_x
    by = base_y + breath_y

    # Floor shadow
    draw.ellipse([bx - 68, base_y - 8, bx + 68, base_y + 16], fill=(6, 18, 23))

    # Shalwar (loose traditional trousers)
    draw.polygon([(bx - 42, by - 145), (bx - 8, by - 145), (bx - 16, base_y), (bx - 48, base_y)], fill=(238, 236, 226))
    draw.polygon([(bx + 8, by - 145), (bx + 42, by - 145), (bx + 48, base_y), (bx + 16, base_y)], fill=(238, 236, 226))

    # Peshawari / dark chappal sandals
    draw.rounded_rectangle([bx - 52, base_y - 14, bx - 12, base_y + 4], radius=7, fill=(68, 38, 18))
    draw.rounded_rectangle([bx + 12, base_y - 14, bx + 52, base_y + 4], radius=7, fill=(68, 38, 18))

    # Long Kurta + open waistcoat/chadar accent
    draw.rounded_rectangle([bx - 48, by - 285, bx + 48, by - 130], radius=18, fill=(248, 246, 238), outline=(180, 140, 60), width=3)
    draw.rounded_rectangle([bx - 44, by - 282, bx + 44, by - 175], radius=14, fill=(20, 92, 82))

    # Calm hands resting gently (no stick waving)
    draw.line([(bx - 44, by - 255), (bx - 56, by - 185)], fill=(248, 246, 238), width=16)
    draw.ellipse([bx - 64, by - 192, bx - 48, by - 176], fill=(244, 185, 128))

    draw.line([(bx + 44, by - 255), (bx + 56, by - 185)], fill=(248, 246, 238), width=16)
    draw.ellipse([bx + 48, by - 192, bx + 64, by - 176], fill=(244, 185, 128))

    # Head & beard (calm expression, no rapid mouth jitter)
    hx = bx
    hy = by - 335
    draw.ellipse([hx - 38, hy - 40, hx + 38, hy + 40], fill=(244, 185, 128), outline=(110, 65, 30), width=2)
    draw.polygon([(hx - 32, hy + 4), (hx + 32, hy + 4), (hx + 22, hy + 46), (hx - 22, hy + 46)], fill=(65, 72, 80))
    draw.ellipse([hx - 16, hy - 8, hx - 7, hy + 1], fill=(20, 24, 28))
    draw.ellipse([hx + 7, hy - 8, hx + 16, hy + 1], fill=(20, 24, 28))
    draw.line([(hx - 8, hy + 14), (hx + 8, hy + 14)], fill=(110, 65, 30), width=2)

    # Topi (white/cream skullcap)
    draw.rounded_rectangle([hx - 38, hy - 58, hx + 38, hy - 26], radius=16, fill=(255, 255, 255), outline=(217, 155, 38), width=2)


def draw_curtains_overlay(draw: ImageDraw.ImageDraw, open_progress: float):
    p = max(0.0, min(1.0, open_progress))
    eased = 1.0 - ((1.0 - p) ** 2.4)
    max_w = (WIDTH // 2) + 25
    cur_w = int(max_w * (1.0 - eased))
    if cur_w <= 6:
        return

    folds = 7
    fold_w = max(1, cur_w // folds)
    top_y = 224
    bot_y = HEIGHT - 162

    for i in range(folds):
        x1 = i * fold_w
        x2 = min(cur_w, (i + 1) * fold_w)
        if x2 > x1:
            clr = (153, 27, 27) if i % 2 == 0 else (185, 28, 28)
            draw.rectangle([x1, top_y, x2, bot_y], fill=clr)
    left_trim_x1 = max(0, cur_w - 14)
    if cur_w > left_trim_x1:
        draw.rectangle([left_trim_x1, top_y, cur_w, bot_y], fill=(245, 158, 11))

    right_start = WIDTH - cur_w
    for i in range(folds):
        x1 = right_start + (i * fold_w)
        x2 = min(WIDTH, right_start + ((i + 1) * fold_w))
        if x2 > x1:
            clr = (153, 27, 27) if i % 2 == 0 else (185, 28, 28)
            draw.rectangle([x1, top_y, x2, bot_y], fill=clr)
    right_trim_x2 = min(WIDTH, right_start + 14)
    if right_trim_x2 > right_start:
        draw.rectangle([right_start, top_y, right_trim_x2, bot_y], fill=(245, 158, 11))


def make_slide(
    top_heading: str,
    badge_label: str,
    badge_color: tuple[int, int, int],
    main_text: str,
    sub_text: str,
    out_path: Path,
    header_font,
    badge_font,
    body_font,
    sub_font,
    t_sec: float = 0.0,
    curtain_progress: float = 1.0,
    darken: bool = False,
):
    img = Image.new("RGB", (WIDTH, HEIGHT), (10, 31, 38))
    draw = ImageDraw.Draw(img)

    # Top & bottom bars
    draw.rectangle([0, 0, WIDTH, 200], fill=(16, 185, 129))
    draw.rectangle([0, 200, WIDTH, 214], fill=(245, 158, 11))
    draw_centered_text(draw, top_heading, WIDTH // 2, 50, header_font, (255, 255, 255))

    draw.rectangle([0, HEIGHT - 155, WIDTH, HEIGHT], fill=(15, 118, 110))
    draw.rectangle([0, HEIGHT - 168, WIDTH, HEIGHT - 155], fill=(245, 158, 11))
    draw_centered_text(draw, "الحمد للہ", WIDTH // 2, HEIGHT - 120, header_font, (254, 243, 199))

    # Unique Islamic background set
    draw_islamic_set_background(draw, t_sec=t_sec, darken=darken)

    # Question/Answer card framed cleanly clear of bottom Shorts bar and right buttons
    card_left = 262
    card_right = WIDTH - 110
    card_top = 250
    card_bottom = HEIGHT - 340
    card_fill = (242, 236, 216) if darken else (255, 251, 235)
    draw.rounded_rectangle(
        [card_left, card_top, card_right, card_bottom],
        radius=34,
        fill=card_fill,
        outline=(217, 119, 6),
        width=9,
    )

    card_cx = (card_left + card_right) // 2
    badge_w = 340
    badge_h = 104
    bx1 = card_cx - (badge_w // 2)
    by1 = card_top + 36
    draw.rounded_rectangle(
        [bx1, by1, bx1 + badge_w, by1 + badge_h],
        radius=24,
        fill=badge_color,
        outline=(255, 255, 255),
        width=3,
    )
    draw_centered_text(draw, badge_label, card_cx, by1 + 18, badge_font, (255, 255, 255))

    max_text_w = (card_right - card_left) - 64
    ur_lines = wrap_text(draw, main_text, body_font, max_text_w)
    en_lines = wrap_text(draw, sub_text, sub_font, max_text_w) if sub_text.strip() else []

    measured = []
    for line in ur_lines:
        bb = draw.textbbox((0, 0), line, font=body_font)
        lh = (bb[3] - bb[1]) + 28
        measured.append((line, body_font, (17, 24, 39), lh))

    if en_lines:
        measured.append(("", sub_font, (75, 85, 99), 20))
        for line in en_lines:
            bb = draw.textbbox((0, 0), line, font=sub_font)
            lh = (bb[3] - bb[1]) + 14
            measured.append((line, sub_font, (75, 85, 99), lh))

    total_h = sum(lh for _, _, _, lh in measured)
    text_area_top = by1 + badge_h + 40
    text_area_bottom = card_bottom - 36
    cur_y = text_area_top + max(0, ((text_area_bottom - text_area_top) - total_h) // 2)

    for line, fnt, clr, lh in measured:
        if line:
            draw_centered_text(draw, line, card_cx, cur_y, fnt, clr)
        cur_y += lh

    # Molvi in Kurta Shalwar & Topi standing calmly above Shorts bottom UI
    draw_molvi_kurta_shalwar_topi(draw, base_x=135, base_y=HEIGHT - 335, t_sec=t_sec)

    if curtain_progress < 1.0:
        draw_curtains_overlay(draw, curtain_progress)

    img.save(out_path, format="PNG")


def build_animated_segment(
    segment_dir: Path,
    duration_sec: float,
    out_mp4: Path,
    frame_builder,
    audio_path: Path | None = None,
    global_t_start: float = 0.0,
):
    segment_dir.mkdir(parents=True, exist_ok=True)
    total_frames = max(6, int(round(duration_sec * FPS)))
    for idx in range(total_frames):
        local_t = idx / FPS
        abs_t = global_t_start + local_t
        progress = idx / max(1, total_frames - 1)
        frame_file = segment_dir / f"f_{idx:04d}.png"
        frame_builder(frame_file, local_t, abs_t, progress)

    raw_video = segment_dir / "raw_video.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", str(segment_dir / "f_%04d.png"),
            "-r", str(FPS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(raw_video),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    if audio_path and audio_path.exists():
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(raw_video),
                "-i", str(audio_path),
                "-filter_complex",
                f"[1:a]aformat=sample_fmts=fltp:sample_rates={AUDIO_RATE}:channel_layouts=stereo,apad=pad_dur=0.1[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-t", f"{duration_sec:.2f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", str(AUDIO_RATE), "-ac", "2", "-b:a", "128k",
                str(out_mp4),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(raw_video),
                "-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo",
                "-t", f"{duration_sec:.2f}",
                "-r", str(FPS),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", str(AUDIO_RATE), "-ac", "2", "-b:a", "128k",
                "-shortest",
                str(out_mp4),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


def render_multi_qa_video(
    batch_items: list[dict],
    run_num: int,
    header_font,
    badge_font,
    body_font,
    sub_font,
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch_work = WORK_DIR / f"run_{run_num:03d}"
    if batch_work.exists():
        shutil.rmtree(batch_work)
    batch_work.mkdir(parents=True, exist_ok=True)

    all_clips = []
    global_t = 0.0

    for q_num, item in enumerate(batch_items, start=1):
        question = item["question"].strip()
        question_en = (item.get("question_en") or "").strip()
        answer = item["answer"].strip()
        answer_en = (item.get("answer_en") or "").strip()
        spoken_q = to_spoken_urdu(item.get("spoken_q") or f"سوال: {question}")
        spoken_a = to_spoken_urdu(item.get("spoken_a") or f"جواب: {answer}")

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
        else:
            q_tts = None
            a_tts = None
            q_dur = 2.5
            a_dur = 2.5

        def build_q_frame(out_p: Path, local_t: float, abs_t: float, _prog: float):
            c_prog = min(1.0, local_t / CURTAIN_OPEN_SEC) if q_num == 1 else 1.0
            make_slide(
                "بسم اللہ الرحمن الرحیم",
                f"سوال {q_num}",
                (217, 119, 6),
                question,
                question_en,
                out_p,
                header_font,
                badge_font,
                body_font,
                sub_font,
                t_sec=abs_t,
                curtain_progress=c_prog,
                darken=False,
            )

        def build_p_frame(out_p: Path, _local_t: float, abs_t: float, _prog: float):
            make_slide(
                "بسم اللہ الرحمن الرحیم",
                f"سوال {q_num}",
                (217, 119, 6),
                question,
                question_en,
                out_p,
                header_font,
                badge_font,
                body_font,
                sub_font,
                t_sec=abs_t,
                curtain_progress=1.0,
                darken=True,
            )

        def build_a_frame(out_p: Path, _local_t: float, abs_t: float, _prog: float):
            make_slide(
                "بسم اللہ الرحمن الرحیم",
                f"جواب {q_num}",
                (5, 150, 105),
                answer,
                answer_en,
                out_p,
                header_font,
                badge_font,
                body_font,
                sub_font,
                t_sec=abs_t,
                curtain_progress=1.0,
                darken=False,
            )

        build_animated_segment(
            batch_work / f"seg_q_{q_num}",
            q_dur,
            q_clip,
            build_q_frame,
            audio_path=q_tts,
            global_t_start=global_t,
        )
        global_t += q_dur

        build_animated_segment(
            batch_work / f"seg_p_{q_num}",
            PAUSE_SEC,
            p_clip,
            build_p_frame,
            audio_path=None,
            global_t_start=global_t,
        )
        global_t += PAUSE_SEC

        build_animated_segment(
            batch_work / f"seg_a_{q_num}",
            a_dur,
            a_clip,
            build_a_frame,
            audio_path=a_tts,
            global_t_start=global_t,
        )
        global_t += a_dur

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

    header_font = get_urdu_font(42)
    badge_font = get_urdu_font(44)
    body_font = get_urdu_font(50)
    sub_font = get_latin_font(30)

    created = render_multi_qa_video(
        batch_items,
        run_num,
        header_font,
        badge_font,
        body_font,
        sub_font,
    )

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
