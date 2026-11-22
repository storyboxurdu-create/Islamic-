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

HISTORY_FILE = Path("islamic_long_history.json")
OUTPUT_VIDEO = Path("final_islamic_long.mp4")
OUTPUT_META = Path("long_meta.json")
OUTPUT_THUMBNAIL = Path("long_thumbnail.jpg")

LOCAL_MUSIC_CANDIDATES = [
    Path("assets/moody_music.mp3"),
    Path("assets/background_music.mp3"),
    Path("moody_music.mp3"),
    Path("background_music.mp3"),
]

LOCAL_CLIP_DIRS = [
    Path("assets/long_clips"),
    Path("assets/clips"),
    Path("assets"),
]

FONT_SOURCES = [
    (
        "Noto Naskh Arabic",
        "https://github.com/google/fonts/raw/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf",
        "NotoNaskhArabic.ttf",
    ),
    (
        "Noto Nastaliq Urdu",
        "https://github.com/google/fonts/raw/main/ofl/notonastaliqurdu/NotoNastaliqUrdu%5Bwght%5D.ttf",
        "NotoNastaliqUrdu.ttf",
    ),
]

MOODY_MUSIC_SOURCES = [
    "https://archive.org/download/relaxing-ambient-piano-music/Relaxing%20Ambient%20Piano%20Music.mp3",
    "https://archive.org/download/DarkAmbientMusic/Dark%20Ambient%201.mp3",
    "https://archive.org/download/SadPianoInstrumental/Sad%20Piano%20Instrumental.mp3",
]

TOPIC_POOL = [
    "Dajjal ka fitna, uski aamad ki nishaniyan aur iman bachane ka mukammal sabaq",
    "Yajooj Majooj ka zikr, deewar ka qissa aur aane wale waqt ki poori yaad-dihani",
    "Aakhri Zamana ke halaat, dil ki ghaflat aur bedar rehne ka mukammal paigham",
    "Hadees ki roshni mein zindagi, aakhirat aur amal ka poora sabaq",
    "Nabiyon ke sachay waqiat se aazmaish, sabr aur kamyabi ki mukammal kahani",
    "Sahaba ke sachay aur pyaray waqiat se sachai, eesar aur yaqeen ki poori dastan",
]

TARGET_CLIPS_COUNT = 32
MIN_TARGET_DURATION_SEC = 185.0  # ~3m 05s


def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    "used_ids": [str(x) for x in (data.get("used_ids") or [])],
                    "recent_summaries": [str(x) for x in (data.get("recent_summaries") or [])],
                }
        except Exception:
            pass
    return {"used_ids": [], "recent_summaries": []}


def save_history(history: dict) -> None:
    payload = {
        "used_ids": (history.get("used_ids") or [])[-120:],
        "recent_summaries": (history.get("recent_summaries") or [])[-15:],
    }
    HISTORY_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_json_object(raw_text: str) -> dict | None:
    cleaned = re.sub(r"```(?:json)?|```", "", raw_text).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _has_urdu_script(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


def _normalize_urdu_pronunciation(text: str) -> str:
    no_latin = re.sub(r"[A-Za-z0-9]+", " ", text)
    no_symbols = re.sub(r"[“”\"'`~@#$%^&*_+=<>|/\\\[\]()]+", " ", no_latin)
    cleaned = re.sub(r"\s*،\s*", "، ", no_symbols)
    cleaned = re.sub(r"\s*[.۔]+\s*", "۔ ", cleaned)
    cleaned = re.sub(r"\s*[؟?]+\s*", "؟ ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _build_dynamic_tags(raw_tags: object, topic: str, title: str, chapters: list[dict]) -> list[str]:
    tags: list[str] = []
    if isinstance(raw_tags, list):
        for t in raw_tags:
            s = str(t).replace("#", "").strip()
            if s and len(s) <= 45 and s not in tags:
                tags.append(s)

    combined = f"{topic} {title} " + " ".join(c.get("narration", "") for c in chapters)
    c_low = combined.lower()

    topic_specific: list[str] = []
    if "dajjal" in c_low or "دجال" in combined:
        topic_specific += ["Dajjal", "Fitna Dajjal", "Dajjal In Islam", "دجال کا فتنہ", "دجال کا واقعہ"]
    if "yajooj" in c_low or "majooj" in c_low or "یاجوج" in combined or "ماجوج" in combined:
        topic_specific += ["Yajooj Majooj", "Gog and Magog", "یاجوج ماجوج", "یاجوج ماجوج کا واقعہ"]
    if "aakhri" in c_low or "akhri" in c_low or "آخری زمانہ" in combined or "قیامت" in combined:
        topic_specific += ["Akhri Zamana", "Aakhri Zamana", "آخری زمانہ", "قیامت کی نشانیاں"]
    if "hadees" in c_low or "hadith" in c_low or "حدیث" in combined:
        topic_specific += ["Hadees", "Hadees Sharif", "حدیث نبوی", "حدیث کا واقعہ"]
    if "nabi" in c_low or "nabiyon" in c_low or "نبی" in combined or "انبیاء" in combined:
        topic_specific += ["Nabiyon Ke Waqiat", "Prophet Stories Urdu", "انبیاء کے واقعات", "نبیوں کے سچے واقعات"]
    if "sahaba" in c_low or "صحابی" in combined or "صحابہ" in combined:
        topic_specific += ["Sahaba Ke Waqiat", "Sahaba Stories Urdu", "صحابہ کے واقعات", "صحابہ کے سچے واقعات"]

    reach_tags = [
        "Storybox",
        "Islamic Story Urdu",
        "Urdu Waqiat",
        "Islamic Reminder",
        "Complete Islamic Story",
        "اسلامی واقعات",
        "اردو کہانی",
        "سچے واقعات",
    ]

    for item in topic_specific + reach_tags:
        clean_item = item.replace("#", "").strip()
        if clean_item and len(clean_item) <= 45 and clean_item not in tags:
            tags.append(clean_item)

    final_tags: list[str] = []
    total_len = 0
    for tag in tags[:22]:
        if total_len + len(tag) + 1 <= 460:
            final_tags.append(tag)
            total_len += len(tag) + 1
    return final_tags


def _list_available_gemini_models(api_key: str) -> list[str]:
    encoded_
