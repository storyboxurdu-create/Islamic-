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

NAMAZ_TIMINGS = [
    ("Fajr", "05:15 AM"),
    ("Zuhr", "12:15 PM"),
    ("Asr", "03:45 PM"),
    ("Maghrib", "05:05 PM"),
    ("Isha", "07:00 PM"),
]

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
    out = []
    for ch in text:
        if _has_glyph(font, ch):
            out.append(ch)
    return "".join(out).strip()


def get_urdu_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoNastaliqUrdu-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def get_latin_font(size: int, bold: bool = False):
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
    )
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


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    center_x: int,
    top_y: int,
    font,
    fill,
    shadow: tuple[int, int, int] | None = None,
):
    safe_txt = sanitize_for_font(safe_display_text(text), font)
    if not safe_txt:
        return 0
    bbox = draw.textbbox((0, 0), safe_txt, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = center_x - (w // 2) - bbox[0]
    y = top_y - bbox[1]
    if shadow is not None:
        draw.text((x + 2, y + 2), safe_txt, font=font, fill=shadow)
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


def draw_namaz_clock_set(
    draw: ImageDraw.ImageDraw,
    t_sec: float,
    q_num: int,
    small_font,
    darken: bool = False,
):
    """Draw a live moving clock + fixed 5 Namaz timings board on the left set."""
    wall_col = (10, 27, 34) if darken else (13, 36, 45)
    panel_col = (17, 45, 55) if darken else (22, 58, 70)
    gold_col = (170, 118, 22) if darken else (225, 165, 42)
    face_col = (244, 240, 228) if darken else (255, 252, 242)

    draw.rectangle([0, 214, WIDTH, HEIGHT - 168], fill=wall_col)

    # Left panel container for Clock + Namaz Timings
    panel_x1 = 18
    panel_x2 = 248
    panel_y1 = 242
    panel_y2 = HEIGHT - 340
    draw.rounded_rectangle(
        [panel_x1, panel_y1, panel_x2, panel_y2],
        radius=24,
        fill=panel_col,
        outline=gold_col,
        width=3,
    )

    # Analog clock with continuously moving hands
    cx = (panel_x1 + panel_x2) // 2
    cy = panel_y1 + 92
    r = 66
    draw.ellipse([cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4], fill=gold_col)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=face_col, outline=(30, 41, 59), width=3)

    # Hour tick marks
    for h_idx in range(12):
        ang = math.radians(h_idx * 30 - 90)
        x_in = cx + int((r - 12) * math.cos(ang))
        y_in = cy + int((r - 12) * math.sin(ang))
        x_out = cx + int((r - 4) * math.cos(ang))
        y_out = cy + int((r - 4) * math.sin(ang))
        draw.line([(x_in, y_in), (x_out, y_out)], fill=(30, 41, 59), width=2)

    # Moving hour, minute, and second hands
    sec_angle = math.radians((t_sec * 60.0) - 90.0)
    min_angle = math.radians((t_sec * 6.0) - 90.0)
    hr_angle = math.radians(((q_num * 2.0) + (t_sec * 0.5)) * 30.0 - 90.0)

    draw.line(
        [(cx, cy), (cx + int((r * 0.48) * math.cos(hr_angle)), cy + int((r * 0.48) * math.sin(hr_angle)))],
        fill=(15, 23, 42),
        width=5,
    )
    draw.line(
        [(cx, cy), (cx + int((r * 0.70) * math.cos(min_angle)), cy + int((r * 0.70) * math.sin(min_angle)))],
        fill=(15, 118, 110),
        width=4,
    )
    draw.line(
        [(cx, cy), (cx + int((r * 0.80) * math.cos(sec_angle)), cy + int((r * 0.80) * math.sin(sec_angle)))],
        fill=(185, 28, 28),
        width=2,
    )
    draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=gold_col)

    # Namaz timings title
    title_y = cy + r + 18
    draw_centered_text(draw, "NAMAZ TIMINGS", cx, title_y, small_font, (254, 243, 199))

    # 5 Fixed Namaz rows
    row_y = title_y + 38
    active_idx = (q_num - 1) % len(NAMAZ_TIMINGS)
    for idx, (prayer_name, prayer_time) in enumerate(NAMAZ_TIMINGS):
        is_active = idx == active_idx
        box_fill = (16, 185, 129) if (is_active and not darken) else ((15, 118, 110) if is_active else (14, 42, 52))
        txt_col = (255, 255, 255) if is_active else (226, 232, 240)
        draw.rounded_rectangle(
            [panel_x1 + 10, row_y, panel_x2 - 10, row_y + 62],
            radius=12,
            fill=box_fill,
            outline=gold_col if is_active else (51, 85, 97),
            width=2,
        )
        draw.text((panel_x1 + 18, row_y + 8), prayer_name, font=small_font, fill=txt_col)
        draw.text((panel_x1 + 18, row_y + 32), prayer_time, font=small_font, fill=txt_col)
        row_y += 72


def draw_realistic_molvi(
    draw: ImageDraw.ImageDraw,
    base_x: int,
    base_y: int,
    t_sec: float,
):
    """Draw a more realistic, shaded Molvi character in Kurta, Shalwar, and Topi."""
    breath_y = int(1.5 * math.sin(t_sec * 2.2))
    bx = base_x
    by = base_y + breath_y

    # Ground contact shadow
    draw.ellipse([bx - 64, base_y - 6, bx + 64, base_y + 16], fill=(5, 16, 20))

    # Shalwar with shaded pleats
    draw.polygon([(bx - 40, by - 142), (bx - 6, by - 142), (bx - 16, base_y), (bx - 46, base_y)], fill=(224, 220, 206))
    draw.line([(bx - 28, by - 135), (bx - 32, base_y - 4)], fill=(178, 172, 154), width=2)
    draw.polygon([(bx + 6, by - 142), (bx + 40, by - 142), (bx + 46, base_y), (bx + 16, base_y)], fill=(236, 232, 218))
    draw.line([(bx + 24, by - 135), (bx + 28, base_y - 4)], fill=(185, 180, 162), width=2)

    # Footwear
    draw.rounded_rectangle([bx - 50, base_y - 13, bx - 12, base_y + 4], radius=7, fill=(56, 30, 14))
    draw.rounded_rectangle([bx + 12, base_y - 13, bx + 50, base_y + 4], radius=7, fill=(56, 30, 14))

    # Shaded Kurta + open Islamic waistcoat/chadar
    draw.rounded_rectangle([bx - 46, by - 280, bx + 46, by - 128], radius=18, fill=(242, 238, 224), outline=(150, 120, 62), width=3)
    draw.line([(bx, by - 275), (bx, by - 135)], fill=(195, 188, 170), width=2)
    draw.rounded_rectangle([bx - 43, by - 278, bx + 16, by - 172], radius=14, fill=(17, 78, 70))
    draw.rounded_rectangle([bx + 18, by - 278, bx + 43, by - 172], radius=14, fill=(14, 65, 58))

    # Arms & hands with subtle skin shading
    draw.line([(bx - 43, by - 250), (bx - 54, by - 182)], fill=(232, 226, 210), width=15)
    draw.ellipse([bx - 62, by - 189, bx - 46, by - 173], fill=(224, 162, 106), outline=(125, 76, 36), width=2)

    draw.line([(bx + 43, by - 250), (bx + 54, by - 182)], fill=(232, 226, 210), width=15)
    draw.ellipse([bx + 46, by - 189, bx + 62, by - 173], fill=(224, 162, 106), outline=(125, 76, 36), width=2)

    # Shaded face, eyebrows, nose bridge, beard & topi
    hx = bx
    hy = by - 332
    draw.ellipse([hx - 36, hy - 38, hx + 36, hy + 38], fill=(228, 166, 110), outline=(115, 68, 32), width=2)
    # Subtle cheek/jaw shadow
    draw.pieslice([hx - 36, hy - 38, hx + 36, hy + 38], start=15, end=165, fill=(208, 145, 92))
    # Eyebrows & eyes
    draw.line([(hx - 21, hy - 14), (hx - 6, hy - 16)], fill=(45, 35, 28), width=3)
    draw.line([(hx + 6, hy - 16), (hx + 21, hy - 14)], fill=(45, 35, 28), width=3)
    draw.ellipse([hx - 16, hy - 8, hx - 8, hy], fill=(24, 24, 24))
    draw.ellipse([hx + 8, hy - 8, hx + 16, hy], fill=(24, 24, 24))
    # Nose & calm lips
    draw.line([(hx, hy - 8), (hx - 2, hy + 5)], fill=(140, 86, 44), width=2)
    draw.line([(hx - 8, hy + 13), (hx + 8, hy + 13)], fill=(115, 64, 34), width=2)
    # Full shaded beard
    draw.polygon([(hx - 31, hy + 4), (hx + 31, hy + 4), (hx + 20, hy + 46), (hx - 20, hy + 46)], fill=(52, 56, 62))
    draw.line([(hx, hy + 14), (hx, hy + 43)], fill=(34, 38, 44), width=2)

    # Embroidered skullcap (Topi)
    draw.rounded_rectangle([hx - 36, hy - 55, hx + 36, hy - 25], radius=15, fill=(248, 246, 240), outline=(198, 142, 34), width=2)
    draw.line([(hx - 28, hy - 33), (hx + 28, hy - 33)], fill=(198, 142, 34), width=2)


def draw_curtains_overlay(draw: ImageDraw.ImageDraw, open_progress: float):
    p = max(0.0, min(1.0, open_progress))
    eased = 1.0 - ((1.0 - p) ** 2.4)
    max_w = (WIDTH // 2) + 25
    cur_w = int(max_w * (1.0 - eased))
    if cur_w <= 6:
        return

    folds = 7
    fold_w = max(1, cur_w // folds)
    top_y = 214
    bot_y = HEIGHT - 168

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
    clock_small_font,
    q_num: int = 1,
    t_sec: float = 0.0,
    curtain_progress: float = 1.0,
    darken: bool = False,
):
    img = Image.new("RGB", (WIDTH, HEIGHT), (10, 31, 38))
    draw = ImageDraw.Draw(img)

    # Top & bottom bars
    draw.rectangle([0, 0, WIDTH, 200], fill=(16, 185, 129))
    draw.rectangle([0, 200, WIDTH, 214], fill=(245, 158, 11))
    draw_centered_text(
        draw,
        top_heading,
        WIDTH // 2,
        42,
        header_font,
        (255, 255, 255),
        shadow=(6, 95, 70),
    )

    draw.rectangle([0, HEIGHT - 155, WIDTH, HEIGHT], fill=(15, 118, 110))
    draw.rectangle([0, HEIGHT - 168, WIDTH, HEIGHT - 155], fill=(245, 158, 11))
    draw_centered_text(
        draw,
        "الحمد للہ",
        WIDTH // 2,
        HEIGHT - 128,
        header_font,
        (254, 243, 199),
        shadow=(17, 94, 89),
    )

    # Namaz clock set on left
    draw_namaz_clock_set(draw, t_sec=t_sec, q_num=q_num, small_font=clock_small_font, darken=darken)

    # Question/Answer card
    card_left = 262
    card_right = WIDTH - 108
    card_top = 246
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
    by1 = card_top + 34
    draw.rounded_rectangle(
        [bx1, by1, bx1 + badge_w, by1 + badge_h],
        radius=24,
        fill=badge_color,
        outline=(255, 255, 255),
        width=3,
    )
    draw_centered_text(
        draw,
        badge_label,
        card_cx,
        by1 + 10,
        badge_font,
        (255, 255, 255),
        shadow=(30, 41, 59),
    )

    max_text_w = (card_right - card_left) - 64
    ur_lines = wrap_text(draw, main_text, body_font, max_text_w)
    en_lines = wrap_text(draw, sub_text, sub_font, max_text_w) if sub_text.strip() else []

    measured = []
    for line in ur_lines:
        bb = draw.textbbox((0, 0), line, font=body_font)
        lh = (bb[3] - bb[1]) + 34
        measured.append((line, body_font, (17, 24, 39), (225, 215, 190), lh))

    if en_lines:
        measured.append(("", sub_font, (75, 85, 99), None, 22))
        for line in en_lines:
            bb = draw.textbbox((0, 0), line, font=sub_font)
            lh = (bb[3] - bb[1]) + 15
            measured.append((line, sub_font, (75, 85, 99), None, lh))

    total_h = sum(lh for _, _, _, _, lh in measured)
    text_area_top = by1 + badge_h + 38
    text_area_bottom = card_bottom - 36
    cur_y = text_area_top + max(0, ((text_area_bottom - text_area_top) - total_h) // 2)

    for line, fnt, clr, shd, lh in measured:
        if line:
            draw_centered_text(draw, line, card_cx, cur_y, fnt, clr, shadow=shd)
        cur_y += lh

    # More realistic shaded Molvi in Kurta Shalwar & Topi
    draw_realistic_molvi(draw, base_x=133, base_y=HEIGHT - 335, t_sec=t_sec)

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
    clock_small_font,
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
                clock_small_font,
                q_num=q_num,
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
                clock_small_font,
                q_num=q_num,
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
                clock_small_font,
                q_num=q_num,
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
    body_font = get_urdu_font(52)
    sub_font = get_latin_font(30, bold=True)
    clock_small_font = get_latin_font(20, bold=True)

    created = render_multi_qa_video(
        batch_items,
        run_num,
        header_font,
        badge_font,
        body_font,
        sub_font,
        clock_small_font,
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
