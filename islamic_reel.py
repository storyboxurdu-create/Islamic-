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
OUTPUT_VIDEO = Path("final_short.mp4")
OUTPUT_META = Path("video_meta.json")

FALLBACK_STORIES = [
    {
        "id": "fallback_01_dil_aur_waqt",
        "title": "Aakhri Zamana Aur Dil Ka Sukoon | Islamic Short",
        "scenes": [
            {"text": "Aakhri zamane ki ek badi nishani yeh hogi ke logon ke paas waqt aur sahoolatein to bohat hongi,", "query": "city traffic night lights"},
            {"text": "par dil ka sukoon aur bharosa kam hota jayega.", "query": "rain window moody"},
            {"text": "Ek shakhs subah se shaam tak screens aur shor mein khoya rehta tha,", "query": "smartphone dark night"},
            {"text": "usay lagta tha woh sab kuch jaanta hai,", "query": "people walking crowd"},
            {"text": "par jab achanak aazmaish aayi to uska dil bechain ho gaya.", "query": "storm clouds ocean"},
            {"text": "Phir usne rozana thora waqt nikaal kar Allah ka zikr,", "query": "mosque architecture peaceful"},
            {"text": "istighfar, aur apni nazar aur zuban ki hifazat shuru ki.", "query": "book pages soft light"},
            {"text": "Aakhri zamane ki sab se badi tip yeh hai:", "query": "candle flame dark"},
            {"text": "fitnon se larne se pehle apna dil,", "query": "calm water sunset"},
            {"text": "apna waqt, aur apna aakhri hisab sambhalo.", "query": "sunrise mountain rays"},
            {"text": "Kyunki sukoon shor mein nahi, balkay rab ke qareeb aane mein hai.", "query": "night sky stars"},
            {"text": "Apni rooh aur amal ko aaj hi durust kar lo.", "query": "morning leaves sunlight"},
        ],
    },
    {
        "id": "fallback_02_zuban_aur_fitna",
        "title": "Aakhri Zamana Mein Zuban Ki Hifazat | Islamic Short",
        "scenes": [
            {"text": "Aakhri zamane mein baatein bohat hongi,", "query": "crowded street people"},
            {"text": "par sach aur jhoot ke darmiyan farq dhundla parne lagega.", "query": "fog forest trees mist"},
            {"text": "Ek dost ne bina tehqeeq ke aik baat aage barha di,", "query": "typing phone screen"},
            {"text": "aur us chhoti si baat ne ghar aur rishton mein doori paida kar di.", "query": "empty chair shadow room"},
            {"text": "Jab usay apni ghalti ka ehsaas hua to usne seekha", "query": "man thinking evening"},
            {"text": "ke har suni sunayi baat phailana gunah aur fitne ka darwaza kholta hai.", "query": "fire sparks dark"},
            {"text": "Aakhri zamane ki ahem tip yeh hai:", "query": "river water stones"},
            {"text": "bolne aur share karne se pehle socho", "query": "lake reflection sunset"},
            {"text": "ke kya yeh baat Allah ko razi karegi", "query": "mosque sky dome"},
            {"text": "ya kisi ka dil dukhayegi.", "query": "rain drops leaf"},
            {"text": "Apni zuban ko sambhalna bhi aik badi ibadat hai.", "query": "golden sunlight nature"},
            {"text": "Sach aur khair ki baat hi aage barhao.", "query": "clear blue sky clouds"},
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
        "You are an Islamic content scriptwriter for 35-second vertical YouTube Shorts in Roman Urdu. "
        "Create ONE fresh 'Aakhri Zamana' (End Times) story with a short relatable story and a practical tip at the end. "
        f"Avoid these previous topic IDs/themes: {recent_list}. "
        "Output ONLY a valid JSON object (no markdown, no extra text) with this exact structure:\n"
        "{\n"
        '  "id": "unique_short_snake_case_id",\n'
        '  "title": "Engaging Urdu/English Short Title | Islamic Short",\n'
        '  "scenes": [\n'
        '    {"text": "Short Roman Urdu narration line (7-12 words)", "query": "2-4 English stock video keywords matching this exact line"}\n'
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Include 12 scenes total so total narration is around 105-130 words (~33-38 seconds when spoken in Urdu).\n"
        "- Scenes 1-2: Aakhri zamana sign/hook.\n"
        "- Scenes 3-7: Short realistic story showing the test/situation.\n"
        "- Scenes 8-12: Clear practical tip and spiritual reminder.\n"
        "- Every 'query' must match the exact action/mood of that scene's 'text'."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={urllib.parse.quote(api_key)}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.85},
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
        story_id = str(parsed.get("id") or f"gemini_{random.randint(10000, 99999)}")
        title = str(parsed.get("title") or "Aakhri Zamana Story & Tip | Islamic Short")
        return {"id": story_id, "title": title, "scenes": valid_scenes}
    except Exception as e:
        print(f"Gemini generation failed, using fallback: {e}")
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


async def generate_voice(text: str, mp3_path: Path) -> None:
    communicate = edge_tts.Communicate(text=text, voice="ur-PK-AsadNeural", rate="-4%")
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
                for size_key in ("medium", "large", "small", "
