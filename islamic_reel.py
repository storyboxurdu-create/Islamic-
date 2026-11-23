import hashlib
import json
import os
import random
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SHORT_HISTORY_FILE = Path("islamic_short_history.json")

SHORT_TOPICS = [
    "Hazrat Yousuf (AS) ka sabr aur achanak badalne wala waqia",
    "Hazrat Musa (AS) ke safar ka ek chhota magar gehra sabaq",
    "Hazrat Ibrahim (AS) ka tawakkul aur aazmaish ka ek qissa",
    "Hazrat Sulaiman (AS) ke insaf aur hikmat ka ek waqia",
    "Hazrat Ayub (AS) ki sabr bhari dua ka ek paigham",
    "Hazrat Yunus (AS) ki tawbah aur qabooliyat ka sabaq",
    "Hazrat Dawood (AS) ki himmat aur shukr ka ek waqia",
    "Hazrat Adam (AS) ki tawbah aur maghfirat ka sabaq",
    "Sahaba ka sachai, eesar aur amanatdari ka ek waqia",
    "Hadees ki roshni mein gussa peene, madad ya sachi zuban ka sabaq",
]


def load_short_history() -> dict:
    if SHORT_HISTORY_FILE.exists():
        try:
            data = json.loads(SHORT_HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    "used_hashes": [str(x) for x in (data.get("used_hashes") or [])][-200:],
                    "recent_titles": [str(x) for x in (data.get("recent_titles") or [])][-25:],
                    "recent_hooks": [str(x) for x in (data.get("recent_hooks") or [])][-25:],
                }
        except Exception:
            pass
    return {"used_hashes": [], "recent_titles": [], "recent_hooks": []}


def save_short_history(history: dict, title: str, quote_text: str) -> None:
    norm = re.sub(r"\s+", " ", f"{title} {quote_text}".strip().lower())
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]

    used_hashes = list(history.get("used_hashes") or [])
    if digest not in used_hashes:
        used_hashes.append(digest)

    recent_titles = list(history.get("recent_titles") or [])
    if title and title not in recent_titles:
        recent_titles.append(title)

    recent_hooks = list(history.get("recent_hooks") or [])
    hook_sample = quote_text[:90].strip()
    if hook_sample and hook_sample not in recent_hooks:
        recent_hooks.append(hook_sample)

    payload = {
        "used_hashes": used_hashes[-200:],
        "recent_titles": recent_titles[-25:],
        "recent_hooks": recent_hooks[-25:],
    }
    SHORT_HISTORY_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_json(raw: str) -> dict | None:
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _list_models(api_key: str) -> list[str]:
    enc_key = urllib.parse.quote(api_key)
    for base in (
        f"https://generativelanguage.googleapis.com/v1beta/models?key={enc_key}",
        f"https://generativelanguage.googleapis.com/v1/models?key={enc_key}",
    ):
        try:
            req = urllib.request.Request(base, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            out: list[str] = []
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods") or []
                name = str(m.get("name") or "")
                if not name or (methods and "generateContent" not in methods):
                    continue
                mid = name.split("/")[-1]
                if "gemini" in mid and "embedding" not in mid and "imagen" not in mid and "veo" not in mid:
                    if mid not in out:
                        out.append(mid)
            if out:
                return out
        except Exception:
            pass
    return ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest", "gemini-1.5-flash"]


def _call_gemini(api_key: str, prompt: str, models: list[str]) -> str:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 1.05},
    }
    enc_key = urllib.parse.quote(api_key)
    urls: list[str] = []
    for mid in models:
        urls.append(f"https://generativelanguage.googleapis.com/v1beta/models/{mid}:generateContent?key={enc_key}")
        urls.append(f"https://generativelanguage.googleapis.com/v1/models/{mid}:generateContent?key={enc_key}")

    last_err = None
    for u in urls:
        try:
            req = urllib.request.Request(
                u,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            txt = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
            if txt:
                return txt
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Gemini Short generation failed: {last_err}")


def generate_fresh_short_story(api_key: str | None = None) -> dict:
    key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required to generate fresh non-repeating Short stories.")

    history = load_short_history()
    used_hashes = set(history.get("used_hashes") or [])
    recent_titles = history.get("recent_titles") or []
    recent_hooks = history.get("recent_hooks") or []

    models = _list_models(key)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    for attempt in range(1, 5):
        topic = random.choice(SHORT_TOPICS)
        nonce = random.randint(100000, 999999)
        avoid_titles = " | ".join(recent_titles[-15:]) or "None"
        avoid_hooks = " | ".join(recent_hooks[-10:]) or "None"

        prompt = (
            f"Time: {now_iso} | Unique Short ID #{nonce} | Attempt {attempt}.\n"
            f"Write a BRAND NEW, crisp, emotionally engaging ~40-50 second Urdu YouTube Short story/reminder on:\n"
            f"Topic: {topic}\n\n"
            "STRICT ANTI-REPEAT RULES:\n"
            f"- NEVER repeat or rephrase these recent titles: {avoid_titles}\n"
            f"- NEVER repeat or rephrase these recent openings: {avoid_hooks}\n"
            "- Pick a fresh angle, scene, or lesson so this Short feels completely distinct.\n"
            "- Write in natural spoken URDU SCRIPT (اردو رسم الخط), ~115 to 145 Urdu words, smooth voiceover prose.\n"
            "- Also give 4 short 2-3 word English stock video queries in 'queries'.\n\n"
            "Return ONLY valid JSON:\n"
            "{\n"
            '  "title": "نیا مختصر اردو عنوان",\n'
            '  "narration": "مکمل اردو تحریر تقریباً 125 الفاظ میں",\n'
            '  "dua_or_lesson": "آخری مختصر سبق یا دعا",\n'
            '  "tags": ["اسلامی شارٹس", "Islamic Shorts", "Urdu Waqiat", "Storybox"],\n'
            '  "queries": ["desert sunset sky", "quiet night stars", "flowing river light", "open book pages"]\n'
            "}"
        )

        raw = _call_gemini(key, prompt, models)
        parsed = _extract_json(raw)
        if not parsed:
            continue

        title = str(parsed.get("title") or "").strip()[:95]
        narration = str(parsed.get("narration") or "").strip()
        dua_or_lesson = str(parsed.get("dua_or_lesson") or "").strip()
        full_text = f"{narration} {dua_or_lesson}".strip()

        if not title or len(full_text.split()) < 65:
            continue

        norm = re.sub(r"\s+", " ", f"{title} {full_text}".strip().lower())
        digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
        if digest in used_hashes or title in recent_titles:
            print(f"Attempt {attempt} matched history; retrying for a fresh story...")
            continue

        raw_tags = parsed.get("tags")
        tags = [str(t).strip() for t in raw_tags if str(t).strip()][:15] if isinstance(raw_tags, list) else []
        if not tags:
            tags = ["اسلامی شارٹس", "Islamic Shorts", "Urdu Waqiat", "Storybox"]

        raw_q = parsed.get("queries")
        queries = [str(q).strip() for q in raw_q if str(q).strip()][:8] if isinstance(raw_q, list) else []
        if not queries:
            queries = ["desert sunset sky", "quiet night stars", "flowing river light", "open book pages"]

        save_short_history(history, title, full_text)
        print(f"Fresh Short story generated: '{title}' ({len(full_text.split())} words)")
        return {
            "id": f"short_{nonce}",
            "title": title,
            "narration": full_text,
            "tags": tags,
            "queries": queries,
        }

    raise RuntimeError("Could not generate a unique non-repeated Short story after multiple attempts.")
