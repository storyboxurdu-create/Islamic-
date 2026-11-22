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

FALLBACK_STORIES = [
    {
        "id": "fallback_sabr_yaqeen",
        "title": "سخت آزمائش میں صبر اور یقین کی سچی کہانی",
        "thumb_text": "آزمائش میں یقین کا کمال",
        "summary": "A story of patience, sincerity, and reliance on Allah during hardship.",
        "tags": ["Islamic Story Urdu", "Urdu Waqiat", "Islamic Reminder", "Storybox", "سچے واقعات"],
        "chapters": [
            {
                "heading": "باب اول",
                "narration": "ایک پرانے شہر میں ایک نیک اور محنتی انسان رہتا تھا جو دن رات حلال روزی کمانے کی کوشش کرتا اور ہر حال میں اللہ کا شکر ادا کرتا تھا۔ ایک وقت ایسا آیا جب کاروبار میں سخت نقصان ہوا اور حالات بالکل بدل گئے، مگر اس کا دل امید اور یقین سے خالی نہیں ہوا۔",
                "scene_beats": [
                    {"line": "ایک پرانے شہر میں نیک انسان", "query": "ancient stone city"},
                    {"line": "حلال روزی کی محنت", "query": "worker walking road"},
                    {"line": "کاروبار میں سخت نقصان", "query": "dark stormy clouds"},
                    {"line": "دل میں امید کا چراغ", "query": "candle light dark"},
                ],
            },
            {
                "heading": "باب دوم",
                "narration": "لوگوں نے مشورے دیے کہ شارٹ کٹ اپنا لو یا شکوہ کرو، مگر اس نے صبر کا دامن تھامے رکھا۔ وہ جانتا تھا کہ ہر رات کے بعد صبح ضرور آتی ہے اور سچائی کبھی رائیگاں نہیں جاتی۔",
                "scene_beats": [
                    {"line": "لوگوں کے مختلف مشورے", "query": "people talking street"},
                    {"line": "صبر کا دامن تھامے رکھنا", "query": "calm hands praying"},
                    {"line": "رات کے بعد صبح کی امید", "query": "sunrise over horizon"},
                    {"line": "سچائی کی مضبوط بنیاد", "query": "mountain rock cliff"},
                ],
            },
            {
                "heading": "باب سوم",
                "narration": "تنہائی کے لمحوں میں وہ سجدے میں جا کر اپنے رب سے دعا کرتا اور دل کو سکون دیتا۔ اس نے کبھی کسی کا حق نہیں مارا اور مشکل وقت میں بھی دوسروں کی خیر خواہی کرتا رہا۔",
                "scene_beats": [
                    {"line": "تنہائی کے خاموش لمحے", "query": "quiet night sky"},
                    {"line": "سجدے اور دعا کا سکون", "query": "peaceful mosque interior"},
                    {"line": "کسی کا حق نہ مارنا", "query": "balance scale light"},
                    {"line": "دوسروں کی خیر خواہی", "query": "helping hand warmth"},
                ],
            },
            {
                "heading": "باب چہارم",
                "narration": "رفتہ رفتہ حالات سنورنے لگے اور غیر متوقع دروازے کھل گئے۔ یہ واقعہ ہمیں سکھاتا ہے کہ صبر، اخلاص اور اللہ پر بھروسہ انسان کو ہر مشکل سے نکال کر کامیابی عطا کرتا ہے۔",
                "scene_beats": [
                    {"line": "حالات کا بدلنا", "query": "flowing river sunlight"},
                    {"line": "نئے راستوں کا کھلنا", "query": "open path forest"},
                    {"line": "صبر اور اخلاص کا پھل", "query": "golden wheat field"},
                    {"line": "اللہ پر مکمل بھروسہ", "query": "clear blue sky"},
                ],
            },
        ],
    },
    {
        "id": "fallback_aakhri_waqt_bedari",
        "title": "غفلت سے بیداری تک کا عبرت ناک سبق",
        "thumb_text": "غفلت چھوڑو اور بیدار ہو جاؤ",
        "summary": "A reminder to stay mindful, sincere, and prepared for the hereafter.",
        "tags": ["Akhri Zamana", "Islamic Reminder", "Urdu Waqiat", "Storybox", "آخری زمانہ"],
        "chapters": [
            {
                "heading": "باب اول",
                "narration": "وقت تیزی سے گزرتا جا رہا ہے اور انسان اکثر روزمرہ کی مصروفیات میں کھو کر اصل مقصد بھول جاتا ہے۔ جب دل پر غفلت چھا جائے تو چھوٹی باتیں بھی بڑی نظر آنے لگتی ہیں اور نیکی کی طرف قدم سست پڑ جاتے ہیں۔",
                "scene_beats": [
                    {"line": "وقت کی تیز رفتار", "query": "clock gears motion"},
                    {"line": "روزمرہ کی مصروفیات", "query": "busy city crowd"},
                    {"line": "دل پر غفلت کے سائے", "query": "misty dark forest"},
                    {"line": "نیکی میں سستی کا احساس", "query": "fading light shadow"},
                ],
            },
            {
                "heading": "باب دوم",
                "narration": "علم اور نصیحت تبھی فائدہ دیتی ہے جب انسان اپنے اعمال کا محاسبہ کرے۔ سچی توبہ اور اصلاح کا دروازہ ہمیشہ کھلا رہتا ہے، بشرطیکہ دل میں پچھتاوا اور بدلنے کا سچا ارادہ موجود ہو۔",
                "scene_beats": [
                    {"line": "اعمال کا محاسبہ", "query": "open book page"},
                    {"line": "سچی توبہ کی روشنی", "query": "sunbeam in dark"},
                    {"line": "دل میں بدلنے کا ارادہ", "query": "calm ocean waves"},
                    {"line": "اصلاح کی طرف پہلا قدم", "query": "footsteps on sand"},
                ],
            },
            {
                "heading": "باب سوم",
                "narration": "جو شخص زبان کی حفاظت کرتا ہے، وعدہ نبھاتا ہے اور کمزوروں پر رحم کرتا ہے، وہ اپنے کردار کو مضبوط بناتا ہے۔ دنیا کی چمک دمک عارضی ہے مگر نیک عمل ہمیشہ ساتھ رہتے ہیں۔",
                "scene_beats": [
                    {"line": "زبان اور وعدے کی پاسداری", "query": "calm water reflection"},
                    {"line": "کمزوروں پر رحم و کرم", "query": "warm sunset light"},
                    {"line": "دنیا کی عارضی چمک", "query": "city lights night"},
                    {"line": "نیک عمل کا باقی رہنا", "query": "tall trees wind"},
                ],
            },
            {
                "heading": "باب چہارم",
                "narration": "آج ہی اپنے دل کو جھنجھوڑیے، نماز اور ذکر کو اپنی زندگی کا حصہ بنائیے اور ہر لمحہ اس طرح جییے کہ حساب کا دن سامنے ہو۔ یہی سمجھداری اور اصل کامیابی کا راستہ ہے۔",
                "scene_beats": [
                    {"line": "دل کو بیدار کرنے کی گھڑی", "query": "dawn sky clouds"},
                    {"line": "نماز اور ذکر کی برکت", "query": "serene landscape view"},
                    {"line": "آخرت کی تیاری کا شعور", "query": "starry night sky"},
                    {"line": "حقیقی کامیابی کا پیغام", "query": "bright morning light"},
                ],
            },
        ],
    },
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
    encoded_key = urllib.parse.quote(api_key)
    for base in (
        f"https://generativelanguage.googleapis.com/v1beta/models?key={encoded_key}",
        f"https://generativelanguage.googleapis.com/v1/models?key={encoded_key}",
    ):
        req = urllib.request.Request(base, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            names: list[str] = []
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods") or []
                full_name = str(m.get("name") or "")
                if not full_name:
                    continue
                if methods and "generateContent" not in methods:
                    continue
                model_id = full_name.split("/")[-1]
                if "gemini" in model_id and "embedding" not in model_id and "imagen" not in model_id and "veo" not in model_id:
                    if model_id not in names:
                        names.append(model_id)
            if names:
                print(f"Discovered Gemini models: {', '.join(names[:8])}")
                return names
        except Exception as e:
            print(f"ListModels check failed ({base.split('?')[0]}): {e}")
    return []


def _call_gemini_json(api_key: str, prompt: str) -> dict:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.95},
    }
    encoded_key = urllib.parse.quote(api_key)
    discovered = _list_available_gemini_models(api_key)
    candidate_models = discovered or [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest",
        "gemini-1.5-flash",
    ]

    endpoints: list[str] = []
    for model_id in candidate_models:
        endpoints.append(f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={encoded_key}")
        endpoints.append(f"https://generativelanguage.googleapis.com/v1/models/{model_id}:generateContent?key={encoded_key}")

    payload = None
    last_err = None
    for url in endpoints:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                break
        except Exception as e:
            last_err = e
            print(f"Endpoint failed ({url.split('?')[0]}): {e}")

    if not payload:
        raise RuntimeError(f"All Gemini endpoints failed: {last_err}")

    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text_out = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    parsed = _extract_json_object(text_out)
    if not parsed:
        raise RuntimeError("Gemini did not return valid JSON.")
    return parsed


def _parse_part_chapters(parsed: dict, default_queries: list[str]) -> list[dict]:
    chapters = parsed.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise RuntimeError("No chapters found in Gemini response.")

    cleaned: list[dict] = []
    for item in chapters:
        if not isinstance(item, dict):
            continue
        raw_narration = _normalize_urdu_pronunciation(str(item.get("narration") or ""))
        if not _has_urdu_script(raw_narration) or len(raw_narration.split()) < 10:
            continue

        raw_beats = item.get("scene_beats")
        beats: list[dict] = []
        if isinstance(raw_beats, list):
            for b in raw_beats:
                if isinstance(b, dict):
                    b_txt = _normalize_urdu_pronunciation(str(b.get("line") or ""))
                    b_q = str(b.get("query") or "").strip()
                    if _has_urdu_script(b_txt) and b_q:
                        beats.append({"line": b_txt, "query": b_q})

        if not beats:
            words = raw_narration.split()
            chunk_sz = max(6, len(words) // 4)
            for idx, start_i in enumerate(range(0, len(words), chunk_sz)):
                piece = " ".join(words[start_i : start_i + chunk_sz]).strip()
                if piece:
                    beats.append({
                        "line": piece,
                        "query": default_queries[idx % len(default_queries)],
                    })

        cleaned.append({
            "heading": _normalize_urdu_pronunciation(str(item.get("heading") or "واقعہ")),
            "narration": raw_narration,
            "scene_beats": beats,
        })

    if not cleaned:
        raise RuntimeError("No valid Urdu chapters parsed.")
    return cleaned


def _get_fallback_story(chosen_topic: str, run_nonce: int, history: dict) -> dict:
    used_ids = set(history.get("used_ids") or [])
    pool = [s for s in FALLBACK_STORIES if s["id"] not in used_ids] or FALLBACK_STORIES
    base = random.choice(pool)
    chapters = [
        {
            "heading": ch["heading"],
            "narration": _normalize_urdu_pronunciation(ch["narration"]),
            "scene_beats": [
                {
                    "line": _normalize_urdu_pronunciation(b["line"]),
                    "query": b["query"],
                }
                for b in ch["scene_beats"]
            ],
        }
        for ch in base["chapters"]
    ]
    tags = _build_dynamic_tags(base.get("tags"), chosen_topic, base["title"], chapters)
    print(f"Using built-in fallback script '{base['title']}' for testing/continuity.")
    return {
        "id": f"{base['id']}_{run_nonce}",
        "title": base["title"],
        "thumb_text": base["thumb_text"],
        "summary": base["summary"],
        "tags": tags,
        "chapters": chapters,
    }


def generate_complete_long_story(api_key: str, history: dict) -> dict:
    recent_summaries = history.get("recent_summaries") or []
    chosen_topic = random.choice(TOPIC_POOL)
    run_nonce = random.randint(100000, 999999)

    if not api_key:
        print("GEMINI_API_KEY missing; falling back to built-in Urdu script.")
        return _get_fallback_story(chosen_topic, run_nonce, history)

    avoid_text = "\n".join(f"- {s}" for s in recent_summaries[-12:]) if recent_summaries else "- None yet"

    part1_prompt = (
        f"Session #{run_nonce} Part 1. Write the FIRST HALF (beginning + rising events) of a COMPLETE, gripping ~3.2-minute "
        f"Urdu Islamic video story on topic: {chosen_topic}.\n"
        "RULES:\n"
        "- Write in natural, clear spoken URDU SCRIPT (اردو رسم الخط) with zero English or Roman words in narration or scene_beats.\n"
        "- Part 1 must contain 4 chapters. Each chapter has ~55-68 Urdu words (~220-260 words total in Part 1).\n"
        "- Every chapter MUST include 4 'scene_beats' where 'line' is a short Urdu phrase from that chapter and 'query' is a 2-3 word English stock video search matching that exact line.\n"
        "- Keep facts respectful and accurate. Do NOT cut off mid-sentence; finish Part 1 cleanly so Part 2 continues the exact story to its complete ending.\n"
        f"AVOID THESE RECENT STORIES:\n{avoid_text}\n"
        "Output ONLY valid JSON:\n"
        "{\n"
        '  "story_title": "مکمل اردو عنوان",\n'
        '  "thumb_text": "تھمب نیل سرخی",\n'
        '  "summary": "Short 1-line summary of the full story",\n'
        '  "tags": ["ٹیگ ایک", "Islamic Story Urdu"],\n'
        '  "chapters": [\n'
        "    {\n"
        '      "heading": "باب اول",\n'
        '      "narration": "مکمل اردو تحریر",\n'
        '      "scene_beats": [\n'
        '        {"line": "اردو جملہ", "query": "desert sand wind"}\n'
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}"
    )

    try:
        p1_data = _call_gemini_json(api_key, part1_prompt)
        p1_chapters = _parse_part_chapters(p1_data, ["desert sand wind", "dark night sky", "ancient stone path", "calm water reflection"])

        story_title = str(p1_data.get("story_title") or "").strip()
        if not _has_urdu_script(story_title):
            story_title = "ایک مکمل اور عبرت ناک واقعہ"

        raw_thumb = _normalize_urdu_pronunciation(str(p1_data.get("thumb_text") or ""))
        thumb_text = raw_thumb if _has_urdu_script(raw_thumb) else _normalize_urdu_pronunciation(story_title).strip()
        summary = str(p1_data.get("summary") or chosen_topic).strip()
        p1_context = " ".join(c["narration"] for c in p1_chapters)

        part2_prompt = (
            f"Session #{run_nonce} Part 2. Continue and COMPLETE the EXACT same Urdu story to its full conclusion and clear lesson.\n"
            f"Story Title: {story_title}\n"
            f"Part 1 so far: {p1_context}\n"
            "RULES:\n"
            "- Write in natural, clear spoken URDU SCRIPT (اردو رسم الخط) with zero English or Roman words in narration or scene_beats.\n"
            "- Part 2 must contain 4 chapters (turning point, climax, complete ending, and final takeaway). Each chapter ~55-68 Urdu words (~220-260 words total in Part 2).\n"
            "- The story MUST reach a complete, satisfying ending—nothing left hanging or incomplete.\n"
            "- Every chapter MUST include 4 'scene_beats' with 'line' (Urdu phrase) and 'query' (2-3 word English stock video query matching that exact line).\n"
            "Output ONLY valid JSON:\n"
            "{\n"
            '  "chapters": [\n'
            "    {\n"
            '      "heading": "باب پنجم",\n'
            '      "narration": "مکمل اردو تحریر",\n'
            '      "scene_beats": [\n'
            '        {"line": "اردو جملہ", "query": "sunrise mountain light"}\n'
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        p2_data = _call_gemini_json(api_key, part2_prompt)
        p2_chapters = _parse_part_chapters(p2_data, ["sunrise mountain light", "quiet prayer night", "open sky clouds", "peaceful river flow"])

        all_chapters = p1_chapters + p2_chapters
        tags = _build_dynamic_tags(p1_data.get("tags"), chosen_topic, story_title, all_chapters)
        story_id = f"long_{run_nonce}"

        total_words = sum(len(c["narration"].split()) for c in all_chapters)
        print(f"Selected topic: {chosen_topic}")
        print(f"Generated complete story '{story_title}' ({len(all_chapters)} chapters, ~{total_words} Urdu words)")
        return {
            "id": story_id,
            "title": story_title,
            "thumb_text": thumb_text,
            "summary": summary,
            "tags": tags,
            "chapters": all_chapters,
        }
    except Exception as e:
        print(f"Gemini generation failed ({e}); using fallback script.")
        return _get_fallback_story(chosen_topic, run_nonce, history)


def ensure_urdu_font(fonts_dir: Path) -> tuple[str, str]:
    fonts_dir.mkdir(parents=True, exist_ok=True)
    for font_name, url, filename in FONT_SOURCES:
        dest = fonts_dir / filename
        if dest.exists() and dest.stat().st_size > 20_000:
            return font_name, str(dest.resolve())
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp, open(dest, "wb") as out:
                out.write(resp.read())
            if dest.exists() and dest.stat().st_size > 20_000:
                return font_name, str(dest.resolve())
        except Exception as e:
            print(f"Font download failed for {font_name}: {e}")

    fallbacks = [
        ("Noto Naskh Arabic", "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"),
        ("Noto Nastaliq Urdu", "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf"),
        ("DejaVu Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for name, path in fallbacks:
        if os.path.exists(path):
            return name, str(Path(path).resolve())
    return "DejaVu Sans", ""


def _try_elevenlabs_tts(full_text: str, mp3_path: Path) -> bool:
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        return False
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip() or "pNInz6obpgDQGcFmaJgB"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{urllib.parse.quote(voice_id)}"
    payload = {
        "text": full_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.48,
            "similarity_boost": 0.80,
            "style": 0.25,
            "use_speaker_boost": True,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(mp3_path, "wb") as out:
            out.write(resp.read())
        if mp3_path.exists() and mp3_path.stat().st_size > 20_000:
            print("Voice engine: ElevenLabs multilingual_v2")
            return True
    except Exception as e:
        print(f"ElevenLabs TTS fallback to edge-tts: {e}")
    return False


async def _generate_edge_continuous_voice(full_text: str, mp3_path: Path) -> None:
    voice_name = os.getenv("EDGE_TTS_VOICE", "").strip() or "ur-PK-AsadNeural"
    communicate = edge_tts.Communicate(
        text=full_text,
        voice=voice_name,
        rate="-4%",
        pitch="-3Hz",
    )
    await communicate.save(str(mp3_path))


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


def build_long_voice(full_text: str, work_dir: Path, clean_wav: Path) -> float:
    clean_text = _normalize_urdu_pronunciation(full_text)
    raw_mp3 = work_dir / "long_narration.mp3"
    if not _try_elevenlabs_tts(clean_text, raw_mp3):
        print("Voice engine: edge-tts continuous Urdu long narration")
        asyncio.run(_generate_edge_continuous_voice(clean_text, raw_mp3))

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_mp3),
        "-af",
        "highpass=f=70,lowpass=f=11000,volume=1.0",
        "-ar",
        "44100",
        "-ac",
        "1",
        str(clean_wav),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dur = get_media_duration(clean_wav)

    if dur < MIN_TARGET_DURATION_SEC:
        pad_needed = round(MIN_TARGET_DURATION_SEC - dur + 1.0, 2)
        padded_wav = work_dir / "padded_voice.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(clean_wav),
                "-af",
                f"apad=pad_dur={pad_needed}",
                "-ar",
                "44100",
                "-ac",
                "1",
                str(padded_wav),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        padded_wav.replace(clean_wav)
        dur = get_media_duration(clean_wav)

    return dur


def prepare_moody_music_track(duration_sec: float, work_dir: Path, out_wav: Path) -> bool:
    dur = max(60.0, round(duration_sec + 1.0, 2))
    fade_out_st = max(1.0, dur - 2.0)

    for local_path in LOCAL_MUSIC_CANDIDATES:
        if local_path.exists() and local_path.stat().st_size > 10_000:
            cmd = [
                "ffmpeg",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(local_path.resolve()),
                "-t",
                f"{dur}",
                "-af",
                f"highpass=f=85,lowpass=f=2400,volume=0.14,afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out_st}:d=2.0",
                "-ar",
                "44100",
                "-ac",
                "1",
                str(out_wav),
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 10_000:
                print(f"Music source: local repo file '{local_path}'")
                return True

    shuffled_sources = list(MOODY_MUSIC_SOURCES)
    random.shuffle(shuffled_sources)
    for idx, src_url in enumerate(shuffled_sources):
        dl_path = work_dir / f"moody_track_{idx}.mp3"
        req = urllib.request.Request(src_url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp, open(dl_path, "wb") as out:
                out.write(resp.read())
            if dl_path.exists() and dl_path.stat().st_size > 100_000:
                start_offset = random.uniform(5.0, 25.0)
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-stream_loop",
                    "-1",
                    "-ss",
                    f"{start_offset:.2f}",
                    "-i",
                    str(dl_path),
                    "-t",
                    f"{dur}",
                    "-af",
                    f"highpass=f=85,lowpass=f=2400,volume=0.14,afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out_st}:d=2.0",
                    "-ar",
                    "44100",
                    "-ac",
                    "1",
                    str(out_wav),
                ]
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if res.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 10_000:
                    print(f"Music source: downloaded track ({src_url})")
                    return True
        except Exception as e:
            print(f"Music download skipped ({src_url}): {e}")

    print("Music source: none")
    return False


def mix_voice_and_music(voice_wav: Path, music_wav: Path, has_music: bool, mixed_wav: Path) -> None:
    if not has_music or not music_wav.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(voice_wav), "-c:a", "pcm_s16le", str(mixed_wav)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(voice_wav),
        "-i",
        str(music_wav),
        "-filter_complex",
        "[0:a]volume=1.08[v];[1:a]volume=1.0[m];[v][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]",
        "-map",
        "[aout]",
        "-ar",
        "44100",
        "-ac",
        "1",
        str(mixed_wav),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _discover_local_clips(used_local: set[Path]) -> list[Path]:
    found: list[Path] = []
    for folder in LOCAL_CLIP_DIRS:
        if folder.exists() and folder.is_dir():
            for ext in ("*.mp4", "*.mov", "*.mkv", "*.webm"):
                for p in sorted(folder.glob(ext)):
                    if p.is_file() and p.stat().st_size > 20_000 and p.resolve() not in used_local:
                        found.append(p.resolve())
    return found


def pick_local_clip(used_local: set[Path]) -> Path | None:
    candidates = _discover_local_clips(used_local)
    if not candidates:
        used_local.clear()
        candidates = _discover_local_clips(used_local)
    if not candidates:
        return None
    chosen = random.choice(candidates)
    used_local.add(chosen)
    return chosen


def fetch_pixabay_clip(query: str, api_key: str, used_urls: set[str]) -> str | None:
    if not api_key or not query:
        return None
    encoded_q = urllib.parse.quote(query)
    encoded_key = urllib.parse.quote(api_key)
    url = f"https://pixabay.com/api/videos/?key={encoded_key}&q={encoded_q}&per_page=15&safesearch=true"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for hit in data.get("hits", []):
                videos = hit.get("videos", {})
                candidates = []
                for key in ("large", "medium", "small", "tiny"):
                    info = videos.get(key) or {}
                    link = info.get("url")
                    if link:
                        h = info.get("height") or 0
                        w = info.get("width") or 0
                        candidates.append((link, h, w))
                candidates.sort(key=lambda item: (0 if item[1] >= item[2] else 1, -item[1]))
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
        with urllib.request.urlopen(req, timeout=20) as resp, open(dest, "wb") as out:
            out.write(resp.read())
        return dest.exists() and dest.stat().st_size > 50_000
    except Exception as e:
        print(f"Download failed for {url}: {e}")
        return False


def build_fallback_clip(dest: Path, dur: float, idx: int) -> None:
    colors = ["0x0c1322", "0x151e30", "0x101827", "0x192236"]
    c = colors[idx % len(colors)]
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={c}:s=1080x1920:d={dur}",
        "-vf",
        "fps=30",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def edit_pro_clip(raw_path: Path, out_path: Path, dur: float, idx: int) -> bool:
    if idx % 2 == 0:
        crop_w, crop_h = 980, 1742
        x_expr = "(iw-ow)/2 + ((iw-ow)*0.15)*sin(t*0.55)"
        y_expr = "(ih-oh)/2"
    else:
        crop_w, crop_h = 970, 1724
        x_expr = "(iw-ow)/2"
        y_expr = "(ih-oh)/2 + ((ih-oh)*0.13)*cos(t*0.5)"

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=w={crop_w}:h={crop_h}:x='{x_expr}':y='{y_expr}',"
        "scale=1080:1920:flags=lanczos,"
        "eq=contrast=1.10:brightness=0.01:saturation=1.15,"
        f"trim=duration={dur},setpts=PTS-STARTPTS,fps=30"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(raw_path),
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 15_000


def _build_32_scene_slots(chapters: list[dict], total_duration: float) -> list[dict]:
    all_beats: list[dict] = []
    for ch in chapters:
        for b in ch.get("scene_beats") or []:
            all_beats.append({
                "line": str(b.get("line") or "").strip(),
                "query": str(b.get("query") or "dark night sky").strip(),
            })

    if not all_beats:
        all_beats = [{"line": "واقعہ جاری ہے", "query": "dark night sky"}]

    slots: list[dict] = []
    for idx in range(TARGET_CLIPS_COUNT):
        src = all_beats[idx % len(all_beats)]
        slots.append({
            "line": src["line"],
            "query": src["query"],
            "weight": max(3, len(src["line"].split())),
        })

    total_w = sum(s["weight"] for s in slots) or len(slots)
    cursor = 0.0
    for idx, s in enumerate(slots):
        if idx == len(slots) - 1:
            end_t = round(total_duration, 2)
        else:
            end_t = round(min(total_duration, cursor + (total_duration * s["weight"]) / total_w), 2)
        dur = max(2.5, round(end_t - cursor, 2))
        s["start"] = round(cursor, 2)
        s["end"] = round(cursor + dur, 2)
        s["dur"] = dur
        cursor = s["end"]

    if slots:
        slots[-1]["end"] = round(total_duration, 2)
        slots[-1]["dur"] = max(2.5, round(slots[-1]["end"] - slots[-1]["start"], 2))

    return slots


def _format_ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    hours = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = sec % 60
    return f"{hours}:{mins:02d}:{secs:05.2f}"


def _build_caption_chunks_from_slots(slots: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    for s in slots:
        words = s["line"].split()
        if not words:
            continue
        sub_pieces = [" ".join(words[i : i + 4]).strip() for i in range(0, len(words), 4)]
        sub_pieces = [p for p in sub_pieces if p]
        span = max(0.4, s["end"] - s["start"])
        step = span / len(sub_pieces)
        for p_idx, piece in enumerate(sub_pieces):
            st = round(s["start"] + p_idx * step, 2)
            en = round(s["end"] if p_idx == len(sub_pieces) - 1 else s["start"] + (p_idx + 1) * step, 2)
            if en > st:
                chunks.append({"text": piece, "start": st, "end": en})
    return chunks


def _render_ass_on_image_or_video(
    input_media: Path,
    output_media: Path,
    ass_text: str,
    ass_path: Path,
    font_file: str,
    is_still_image: bool = False,
) -> bool:
    ass_path.write_text(ass_text, encoding="utf-8")
    escaped_ass = str(ass_path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    fonts_dir = ""
    if font_file:
        fonts_dir = str(Path(font_file).parent).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    vf_sub = f"subtitles='{escaped_ass}'" + (f":fontsdir='{fonts_dir}'" if fonts_dir else "")
    cmd = ["ffmpeg", "-y", "-i", str(input_media), "-vf", vf_sub]
    if is_still_image:
        cmd += ["-frames:v", "1", "-q:v", "2", str(output_media)]
    else:
        cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p", str(output_media)]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return res.returncode == 0 and output_media.exists() and output_media.stat().st_size > 2000


def generate_thumbnail(first_clip: Path, thumb_text: str, work_dir: Path, font_name: str, font_file: str) -> None:
    base_frame = work_dir / "long_thumb_base.png"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(first_clip),
            "-ss",
            "0.4",
            "-vframes",
            "1",
            "-vf",
            "scale=1080:1920,eq=contrast=1.18:brightness=-0.06:saturation=1.15",
            str(base_frame),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not base_frame.exists() or base_frame.stat().st_size < 2000:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0b1021:s=1080x1920", "-vframes", "1", str(base_frame)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    clean_headline = thumb_text.replace("{", "").replace("}", "").strip() or "مکمل واقعہ اور سبق"
    ass_header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Thumb,{font_name},94,&H0000FFFF,&H0000FFFF,&H00000000,&HB0000000,"
        "-1,0,0,0,105,105,0,0,3,6,4,5,70,70,220,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:05.00,Thumb,,0,0,0,,{clean_headline}\n"
    )
    ok = _render_ass_on_image_or_video(
        base_frame,
        OUTPUT_THUMBNAIL,
        ass_header,
        work_dir / "long_thumb.ass",
        font_file,
        is_still_image=True,
    )
    if not ok:
        subprocess.run(["cp", "-f", str(base_frame), str(OUTPUT_THUMBNAIL)], check=False)


def burn_ass_captions(
    input_video: Path,
    output_video: Path,
    caption_chunks: list[dict],
    ass_path: Path,
    font_name: str,
    font_file: str,
) -> None:
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "Scaled
