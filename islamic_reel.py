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

INTRO_SPOKEN_TEXT = "آئیے، آج کے مشکل اسلامی سوالات کا سلسلہ شروع کرتے ہیں۔"
INTRO_SUB_TEXT = "Islamic Quiz Challenge — Curtain Rises"

HISTORY_FILE = "islamic_history.json"
FINAL_SHORT_FILE = Path("final_islamic_short.mp4")
OUTPUT_DIR = Path("output_reels")
WORK_DIR = Path("work_frames")

UNIQUE_QA_BANK = [
    (
        "قرآن مجید کی کس سورۃ کی ہر آیت میں لفظ 'اللہ' آیا ہے؟",
        "In which Surah of the Quran does the word 'Allah' appear in every verse?",
        "سورۃ المجادلہ۔",
        "Surah Al-Mujadila.",
        "سوال: قرآن مجید کی کس سورہ کی ہر آیت میں لفظ اللہ آیا ہے؟",
        "جواب: سورہ المجادلہ۔",
    ),
    (
        "صلحِ حدیبیہ کس ہجری میں واقع ہوئی؟",
        "In which Hijri year did the Treaty of Hudaybiyyah take place?",
        "چھ (6) ہجری میں۔",
        "In 6 AH.",
        "سوال: صلح حدیبیہ کس ہجری میں واقع ہوئی؟",
        "جواب: چھ ہجری میں۔",
    ),
    (
        "اصطلاحِ حدیث میں 'متواتر' روایت کسے کہتے ہیں؟",
        "In Hadith terminology, what is a 'Mutawatir' narration?",
        "جسے ہر دور میں اتنی کثیر جماعت نے روایت کیا ہو کہ جھوٹ پر اتفاق محال ہو۔",
        "A narration transmitted at every stage by so many narrators that collusion on a lie is inconceivable.",
        "سوال: اصطلاح حدیث میں متواتر روایت کسے کہتے ہیں؟",
        "جواب: جسے ہر دور میں اتنی کثیر جماعت نے بیان کیا ہو کہ جھوٹ پر اتفاق ممکن نہ ہو۔",
    ),
    (
        "قرآن مجید میں کس صحابی کا نام صراحتاً آیا ہے؟",
        "Which Companion's name is explicitly mentioned in the Quran?",
        "حضرت زید بن حارثہ رضی اللہ عنہ۔",
        "Zayd ibn Harithah (may Allah be pleased with him).",
        "سوال: قرآن مجید میں کس صحابی کا نام واضح طور پر آیا ہے؟",
        "جواب: حضرت زید بن حارثہ رضی اللہ عنہ۔",
    ),
    (
        "نزولِ قرآن کے اعتبار سے سب سے پہلی مکمل سورۃ کون سی ہے؟",
        "Which Surah was revealed complete first in chronological order?",
        "سورۃ الفاتحہ۔",
        "Surah Al-Fatihah.",
        "سوال: نزول قرآن کے اعتبار سے سب سے پہلی مکمل سورہ کون سی ہے؟",
        "جواب: سورہ الفاتحہ۔",
    ),
    (
        "قرآن مجید کی کس سورۃ میں دو سجدۂ تلاوت ہیں؟",
        "Which Surah of the Quran contains two verses of prostration (Sajdah Tilawah)?",
        "سورۃ الحج میں۔",
        "In Surah Al-Hajj.",
        "سوال: قرآن مجید کی کس سورہ میں دو سجدہ تلاوت ہیں؟",
        "جواب: سورہ الحج میں۔",
    ),
    (
        "غزوہِ تبوک کس سن ہجری میں پیش آیا؟",
        "In which Hijri year did the Expedition of Tabuk take place?",
        "نو (9) ہجری میں۔",
        "In 9 AH.",
        "سوال: غزوہ تبوک کس سن ہجری میں پیش آیا؟",
        "جواب: نو ہجری میں۔",
    ),
    (
        "قرآن مجید میں سب سے طویل آیت کون سی ہے؟",
        "Which is the longest verse in the Quran?",
        "سورۃ البقرۃ کی آیت نمبر 282 (آیتِ مدائنہ)۔",
        "Verse 282 of Surah Al-Baqarah (the verse on debt/contracts).",
        "سوال: قرآن مجید میں سب سے لمبی آیت کون سی ہے؟",
        "جواب: سورہ البقرہ کی آیت نمبر دو سو بیاسی۔",
    ),
    (
        "نمازِ جنازہ میں کتنی تکبیریں کہی جاتی ہیں؟",
        "How many Takbirs are recited in the funeral prayer (Salat al-Janazah)?",
        "چار تکبیریں۔",
        "Four Takbirs.",
        "سوال: نماز جنازہ میں کتنی تکبیریں کہی جاتی ہیں؟",
        "جواب: چار تکبیریں۔",
    ),
    (
        "صحابہ کرام میں سب سے پہلے کس نے ہجرتِ حبشہ کی قیادت کی؟",
        "Who led the first migration to Abyssinia (Habashah) among the Companions?",
        "حضرت عثمان بن عفان رضی اللہ عنہ (اہلیہ کے ہمراہ)۔",
        "Uthman ibn Affan (may Allah be pleased with him) along with his spouse.",
        "سوال: صحابہ کرام میں سب سے پہلے کس نے ہجرت حبشہ کی قیادت کی؟",
        "جواب: حضرت عثمان بن عفان رضی اللہ عنہ نے اپنی اہلیہ کے ہمراہ۔",
    ),
    (
        "قرآن مجید کی کس سورۃ میں لفظ 'الرحمٰن' بطورِ خاص بار بار آیا ہے؟",
        "In which Surah is the refrain mentioning 'Ar-Rahman' repeated across verses?",
        "سورۃ الرحمٰن میں۔",
        "In Surah Ar-Rahman.",
        "سوال: قرآن مجید کی کس سورہ میں لفظ رحمن بار بار آیا ہے؟",
        "جواب: سورہ رحمن میں۔",
    ),
    (
        "حج کے دوران یومِ عرفہ کس تاریخ کو ہوتا ہے؟",
        "On which date of Dhul-Hijjah does the Day of Arafah fall during Hajj?",
        "نو (9) ذوالحجہ کو۔",
        "On the 9th of Dhul-Hijjah.",
        "سوال: حج کے دوران یوم عرفہ کس تاریخ کو ہوتا ہے؟",
        "جواب: نو ذوالحجہ کو۔",
    ),
    (
        "علمِ اصولِ فقہ میں 'اجماع' سے کیا مراد ہے؟",
        "In Usul al-Fiqh (principles of jurisprudence), what does 'Ijma' mean?",
        "کسی شرعی مسئلے پر امت کے مجتہدین کا ایک دور میں اتفاق۔",
        "Consensus of the qualified jurists (Mujtahids) of the Ummah in an era on a Shariah ruling.",
        "سوال: علم اصول فقہ میں اجماع سے کیا مراد ہے؟",
        "جواب: کسی شرعی مسئلے پر امت کے مجتہدین کا ایک دور میں اتفاق۔",
    ),
    (
        "قرآن مجید میں کس نبی کا ذکر سب سے زیادہ مرتبہ آیا ہے؟",
        "Which Prophet is mentioned most frequently by name in the Quran?",
        "حضرت موسیٰ علیہ السلام۔",
        "Prophet Musa (Moses, peace be upon him).",
        "سوال: قرآن مجید میں کس نبی کا ذکر سب سے زیادہ بار آیا ہے؟",
        "جواب: حضرت موسیٰ علیہ السلام کا۔",
    ),
    (
        "فتحِ مکہ کس سن ہجری میں ہوئی؟",
        "In which Hijri year did the Conquest of Makkah occur?",
        "آٹھ (8) ہجری میں۔",
        "In 8 AH.",
        "سوال: فتح مکہ کس سن ہجری میں ہوئی؟",
        "جواب: آٹھ ہجری میں۔",
    ),
    (
        "نماز میں ہاتھ باندھنے کی حالت کو فقہ کی اصطلاح میں کیا کہتے ہیں؟",
        "What is the standing posture with hands folded in Salah called in Fiqh?",
        "قیام۔",
        "Qiyam.",
        "سوال: نماز میں ہاتھ باندھنے کی حالت کو کیا کہتے ہیں؟",
        "جواب: قیام۔",
    ),
    (
        "قرآن مجید کی کون سی سورۃ 'حوامیم' (حٰمٓ سے شروع ہونے والی سورتوں) میں شامل نہیں ہے؟",
        "Which of these is NOT among the seven 'Hawamim' Surahs starting with Ha-Mim? (Al-Ahqaf, Ash-Shura, Al-Mulk)",
        "سورۃ الملک۔",
        "Surah Al-Mulk.",
        "سوال: قرآن مجید کی کون سی سورہ حوامیم میں شامل نہیں ہے؟",
        "جواب: سورہ ملک۔",
    ),
    (
        "عید الفطر اور عید الاضحیٰ کی نمازیں کس نوعیت کی ہیں؟",
        "What is the ruling status of the Eid al-Fitr and Eid al-Adha prayers in Hanafi Fiqh?",
        "واجب۔",
        "Wajib (obligatory).",
        "سوال: عید الفطر اور عید الاضحی کی نمازیں کس نوعیت کی ہیں؟",
        "جواب: واجب۔",
    ),
    (
        "قرآن مجید کی کس سورۃ کا آغاز 'تبارک' سے ہوتا ہے؟",
        "Which Surah begins with the word 'Tabarak'?",
        "سورۃ الملک اور سورۃ الفرقان۔",
        "Surah Al-Mulk and Surah Al-Furqan.",
        "سوال: قرآن مجید کی کس سورہ کا آغاز تبارک سے ہوتا ہے؟",
        "جواب: سورہ ملک اور سورہ فرقان۔",
    ),
    (
        "مسجدِ اقصیٰ کس شہر میں واقع ہے؟",
        "In which city is Masjid Al-Aqsa located?",
        "بیت المقدس (القدس) میں۔",
        "Jerusalem (Bayt al-Maqdis / Al-Quds).",
        "سوال: مسجد اقصی کس شہر میں واقع ہے؟",
        "جواب: بیت المقدس میں۔",
    ),
    (
        "اصطلاحِ حدیث میں 'صحیح لغیرہٖ' کس حدیث کو کہتے ہیں؟",
        "In Hadith terminology, what is a Hadith classified as 'Sahih li-ghayrihi'?",
        "جو بذاتِ خود حسن ہو مگر متعدد اسانید یا شواہد سے تقویت پا کر صحیح کے درجے تک پہنچ جائے۔",
        "A narration that is Hasan in itself and reaches the level of Sahih through multiple chains or corroborating reports.",
        "سوال: اصطلاح حدیث میں صحیح لغیرہ کس حدیث کو کہتے ہیں؟",
        "جواب: جو خود حسن ہو مگر متعدد سندوں یا شواہد سے تقویت پا کر صحیح کے درجے تک پہنچ جائے۔",
    ),
    (
        "قرآن مجید میں سب سے مختصر سورۃ کون سی ہے؟",
        "Which is the shortest Surah in the Quran?",
        "سورۃ الکوثر۔",
        "Surah Al-Kawthar.",
        "سوال: قرآن مجید میں سب سے مختصر سورہ کون سی ہے؟",
        "جواب: سورہ کوثر۔",
    ),
    (
        "غزوہِ خندق (احزاب) کس سن ہجری میں پیش آیا؟",
        "In which Hijri year did the Battle of the Trench (Al-Ahzab) take place?",
        "پانچ (5) ہجری میں۔",
        "In 5 AH.",
        "سوال: غزوہ خندق کس سن ہجری میں پیش آیا؟",
        "جواب: پانچ ہجری میں۔",
    ),
    (
        "زکوٰۃ کے آٹھ مصارف قرآن مجید کی کس سورۃ میں بیان ہوئے ہیں؟",
        "In which Surah are the eight categories of Zakat recipients mentioned?",
        "سورۃ التوبہ میں۔",
        "In Surah At-Tawbah.",
        "سوال: زکوۃ کے آٹھ مصارف قرآن مجید کی کس سورہ میں بیان ہوئے ہیں؟",
        "جواب: سورہ توبہ میں۔",
    ),
    (
        "قرآن مجید کی کس سورۃ میں حضرت مریم علیہا السلام کا نام آیا ہے؟",
        "In which Surah is Maryam (Mary, peace be upon her) named?",
        "سورۃ مریم (اور دیگر سورتوں میں بھی)۔",
        "Surah Maryam (as well as other Surahs).",
        "سوال: قرآن مجید کی کس سورہ میں حضرت مریم کا نام آیا ہے؟",
        "جواب: سورہ مریم میں۔",
    ),
]


def to_spoken_urdu(text: str) -> str:
    """Clean diacritics and tricky Arabic-script variants so Urdu TTS pronounces words clearly."""
    cleaned = re.sub(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]", "", text)
    replacements = {
        "سورۃ": "سورہ",
        "زکوٰۃ": "زکوۃ",
        "صلوٰۃ": "نماز",
        "حٰمٓ": "حا میم",
        "یٰس": "یاسین",
        "الرحمٰن": "الرحمان",
        "بِسْمِ اللّٰہِ الرَّحْمٰنِ الرَّحِیمِ": "بسم اللہ الرحمن الرحیم",
        "ؤ": "و",
        "ئ": "ی",
        "ى": "ی",
        "ۃ": "ہ",
    }
    for src, dst in replacements.items():
        cleaned = cleaned.replace(src, dst)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


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


def generate_unique_batch(count: int, state: dict) -> list[dict]:
    seen = set(state["seen_questions"])
    fresh = []

    cycle = 0
    while len(fresh) < count:
        for ur_q, en_q, ur_a, en_a, sp_q, sp_a in UNIQUE_QA_BANK:
            q_text = ur_q if cycle == 0 else f"{ur_q} ({cycle + 1})"
            if q_text in seen:
                continue
            fresh.append({
                "question": q_text,
                "question_en": en_q,
                "answer": ur_a,
                "answer_en": en_a,
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


def draw_teacher_with_stick(draw: ImageDraw.ImageDraw, base_x: int, base_y: int, stick_angle_deg: float):
    """Draw a stylized teacher standing on the side holding a pointer stick toward the quiz board."""
    # Shadow on floor
    draw.ellipse([base_x - 75, base_y - 12, base_x + 75, base_y + 18], fill=(6, 20, 25))

    # Legs / trousers
    draw.rounded_rectangle([base_x - 36, base_y - 145, base_x - 6, base_y], radius=10, fill=(30, 41, 59))
    draw.rounded_rectangle([base_x + 6, base_y - 145, base_x + 36, base_y], radius=10, fill=(30, 41, 59))

    # Shoes
    draw.rounded_rectangle([base_x - 46, base_y - 18, base_x - 2, base_y + 4], radius=8, fill=(15, 23, 42))
    draw.rounded_rectangle([base_x + 4, base_y - 18, base_x + 48, base_y + 4], radius=8, fill=(15, 23, 42))

    # Torso / kurta / coat
    draw.rounded_rectangle([base_x - 52, base_y - 295, base_x + 52, base_y - 135], radius=22, fill=(248, 250, 252), outline=(217, 119, 6), width=4)
    # Waistcoat / shawl accent
    draw.rounded_rectangle([base_x - 48, base_y - 292, base_x + 48, base_y - 165], radius=18, fill=(15, 118, 110))

    # Head & cap/turban
    head_cx = base_x
    head_cy = base_y - 345
    draw.ellipse([head_cx - 42, head_cy - 44, head_cx + 42, head_cy + 44], fill=(253, 186, 116), outline=(120, 53, 15), width=3)
    # Beard / stubble detail
    draw.arc([head_cx - 34, head_cy - 8, head_cx + 34, head_cy + 38], start=10, end=170, fill=(55, 65, 81), width=8)
    # Eyes
    draw.ellipse([head_cx - 18, head_cy - 10, head_cx - 8, head_cy], fill=(17, 24, 39))
    draw.ellipse([head_cx + 8, head_cy - 10, head_cx + 18, head_cy], fill=(17, 24, 39))
    # Cap
    draw.rounded_rectangle([head_cx - 44, head_cy - 62, head_cx + 44, head_cy - 24], radius=14, fill=(217, 119, 6))

    # Right arm & hand holding the stick
    shoulder_x = base_x + 36
    shoulder_y = base_y - 260
    hand_x = base_x + 88
    hand_y = base_y - 235
    draw.line([(shoulder_x, shoulder_y), (hand_x, hand_y)], fill=(248, 250, 252), width=20)
    draw.ellipse([hand_x - 14, hand_y - 14, hand_x + 14, hand_y + 14], fill=(253, 186, 116), outline=(120, 53, 15), width=3)

    # Pointer stick extending toward the board
    rad = math.radians(stick_angle_deg)
    stick_len = 250
    end_x = int(hand_x + math.cos(rad) * stick_len)
    end_y = int(hand_y + math.sin(rad) * stick_len)
    draw.line([(hand_x, hand_y), (end_x, end_y)], fill=(146, 64, 14), width=10)
    draw.ellipse([end_x - 8, end_y - 8, end_x + 8, end_y + 8], fill=(245, 158, 11))


def make_intro_frame(
    progress: float,
    out_path: Path,
    header_font,
    body_font,
    sub_font,
):
    """progress in [0.0, 1.0]: curtains open from both sides while teacher points stick to the quiz card."""
    p = max(0.0, min(1.0, progress))
    img = Image.new("RGB", (WIDTH, HEIGHT), (10, 31, 38))
    draw = ImageDraw.Draw(img)

    # Top & bottom bars
    draw.rectangle([0, 0, WIDTH, 210], fill=(16, 185, 129))
    draw.rectangle([0, 210, WIDTH, 224], fill=(245, 158, 11))
    draw_centered_text(draw, "بسم اللہ الرحمن الرحیم", WIDTH // 2, 55, header_font, (255, 255, 255))

    draw.rectangle([0, HEIGHT - 150, WIDTH, HEIGHT], fill=(15, 118, 110))
    draw.rectangle([0, HEIGHT - 162, WIDTH, HEIGHT - 150], fill=(245, 158, 11))
    draw_centered_text(draw, "الحمد للہ", WIDTH // 2, HEIGHT - 115, header_font, (254, 243, 199))

    # Quiz board / card on the right-center where teacher points
    board_left = 290
    board_right = WIDTH - 44
    board_top = 340
    board_bottom = HEIGHT - 320
    draw.rounded_rectangle(
        [board_left, board_top, board_right, board_bottom],
        radius=36,
        fill=(255, 251, 235),
        outline=(217, 119, 6),
        width=10,
    )

    board_cx = (board_left + board_right) // 2
    ur_lines = wrap_text(draw, "مشکل اسلامی سوالات", body_font, (board_right - board_left) - 70)
    en_lines = wrap_text(draw, INTRO_SUB_TEXT, sub_font, (board_right - board_left) - 70)

    cur_y = board_top + 220
    for line in ur_lines:
        h = draw_centered_text(draw, line, board_cx, cur_y, body_font, (17, 24, 39))
        cur_y += h + 30

    cur_y += 25
    for line in en_lines:
        h = draw_centered_text(draw, line, board_cx, cur_y, sub_font, (75, 85, 99))
        cur_y += h + 16

    # Teacher on left holding stick pointing up-right toward the board
    stick_angle = -28.0 + (8.0 * math.sin(p * math.pi))
    draw_teacher_with_stick(draw, base_x=155, base_y=HEIGHT - 215, stick_angle_deg=stick_angle)

    # Opening curtains on left and right edges (retract as progress goes 0 -> 1)
    max_curtain_w = (WIDTH // 2) + 30
    cur_curtain_w = int(max_curtain_w * (1.0 - (0.78 * p)))
    folds = 7
    if cur_curtain_w > 12:
        # Left curtain
        fold_w = max(8, cur_curtain_w // folds)
        for i in range(folds):
            x1 = i * fold_w
            x2 = min(cur_curtain_w, (i + 1) * fold_w)
            clr = (153, 27, 27) if i % 2 == 0 else (185, 28, 28)
            draw.rectangle([x1, 224, x2, HEIGHT - 162], fill=clr)
        draw.rectangle([cur_curtain_w - 14, 224, cur_curtain_w, HEIGHT - 162], fill=(245, 158, 11))

        # Right curtain
        right_start = WIDTH - cur_curtain_w
        for i in range(folds):
            x1 = right_start + (i * fold_w)
            x2 = min(WIDTH, right_start + ((i + 1) * fold_w))
            clr = (153, 27, 27) if i % 2 == 0 else (185, 28, 28)
            draw.rectangle([x1, 224, x2, HEIGHT - 162], fill=clr)
        draw.rectangle([right_start, 224, right_start + 14, HEIGHT - 162], fill=(245, 158, 11))

    img.save(out_path, format="PNG")


def build_curtain_teacher_intro(
    batch_work: Path,
    header_font,
    body_font,
    sub_font,
) -> Path:
    intro_mp4 = batch_work / "intro_curtain_teacher.mp4"
    intro_tts = batch_work / "intro_voice.mp3"
    intro_raw = batch_work / "intro_frames_raw.mp4"

    if USE_VOICE:
        asyncio.run(generate_tts(INTRO_SPOKEN_TEXT, intro_tts))
        duration_sec = max(1.6, get_media_duration(intro_tts) + 0.1)
    else:
        duration_sec = 2.0

    total_frames = max(15, int(round(duration_sec * FPS)))
    frames_dir = batch_work / "intro_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(total_frames):
        progress = idx / max(1, total_frames - 1)
        frame_path = frames_dir / f"f_{idx:04d}.png"
        make_intro_frame(progress, frame_path, header_font, body_font, sub_font)

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", str(frames_dir / "f_%04d.png"),
            "-r", str(FPS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(intro_raw),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    if USE_VOICE and intro_tts.exists():
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(intro_raw),
                "-i", str(intro_tts),
                "-filter_complex",
                f"[1:a]aformat=sample_fmts=fltp:sample_rates={AUDIO_RATE}:channel_layouts=stereo,apad=pad_dur=0.1[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-t", f"{duration_sec:.2f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", str(AUDIO_RATE), "-ac", "2", "-b:a", "128k",
                str(intro_mp4),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        build_silent_segment(frames_dir / "f_0000.png", duration_sec, intro_mp4, darken=False)

    return intro_mp4


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
    ur_lines = wrap_text(draw, main_text, body_font, max_text_w)
    en_lines = wrap_text(draw, sub_text, sub_font, max_text_w) if sub_text.strip() else []

    measured = []
    for line in ur_lines:
        bb = draw.textbbox((0, 0), line, font=body_font)
        lh = (bb[3] - bb[1]) + 34
        measured.append((line, body_font, (17, 24, 39), lh))

    if en_lines:
        measured.append(("", sub_font, (75, 85, 99), 28))
        for line in en_lines:
            bb = draw.textbbox((0, 0), line, font=sub_font)
            lh = (bb[3] - bb[1]) + 18
            measured.append((line, sub_font, (75, 85, 99), lh))

    total_h = sum(lh for _, _, _, lh in measured)
    text_area_top = by1 + badge_h + 65
    text_area_bottom = card_bottom - 55
    cur_y = text_area_top + max(0, ((text_area_bottom - text_area_top) - total_h) // 2)

    for line, fnt, clr, lh in measured:
        if line:
            draw_centered_text(draw, line, WIDTH // 2, cur_y, fnt, clr)
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

    intro_clip = build_curtain_teacher_intro(batch_work, header_font, body_font, sub_font)
    all_clips = [intro_clip]

    for q_num, item in enumerate(batch_items, start=1):
        question = item["question"].strip()
        question_en = (item.get("question_en") or "").strip()
        answer = item["answer"].strip()
        answer_en = (item.get("answer_en") or "").strip()
        spoken_q = to_spoken_urdu(item.get("spoken_q") or f"سوال: {question}")
        spoken_a = to_spoken_urdu(item.get("spoken_a") or f"جواب: {answer}")

        q_img = batch_work / f"q_{q_num}.png"
        a_img = batch_work / f"a_{q_num}.png"

        make_slide(
            "بسم اللہ الرحمن الرحیم",
            f"سوال {q_num}",
            (217, 119, 6),
            question,
            question_en,
            q_img,
            header_font,
            badge_font,
            body_font,
            sub_font,
        )
        make_slide(
            "بسم اللہ الرحمن الرحیم",
            f"جواب {q_num}",
            (5, 150, 105),
            answer,
            answer_en,
            a_img,
            header_font,
            badge_font,
            body_font,
            sub_font,
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
    body_font = get_urdu_font(58)
    sub_font = get_latin_font(34)

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
