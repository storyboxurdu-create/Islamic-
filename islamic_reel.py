import json
import os
import random
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

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


def _clean_title(raw_title: str, fallback_topic: str) -> str:
    cleaned = re.sub(r"[“”\"'`#]+", "", (raw_title or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:،۔")
    return (cleaned[:95] or fallback_topic[:95]).strip()


def generate_fresh_short_story(api_key: str | None = None) -> dict:
    key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required to generate Short stories.")

    models = _list_models(key)
    topic = random.choice(SHORT_TOPICS)
    nonce = random.randint(100000, 999999)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    prompt = (
        f"Time: {now_iso} | Run #{nonce}.\n"
        f"Write a complete ~40-50 second Urdu YouTube Short/Reel story on:\n"
        f"Topic: {topic}\n\n"
        "Rules:\n"
        "- 'title' MUST represent the ENTIRE story/reel from start to finish (its core event and final takeaway)—NOT just a teaser word or opening line.\n"
        "- Write ~115-135 natural spoken Urdu words in 'narration' with a clear beginning, main event, and ending lesson.\n"
        "- Write ONLY in natural spoken Urdu script (اردو رسم الخط), smooth voiceover prose, no bullets or markdown.\n"
        "- Provide 4 short 2-3 word English stock video queries in 'queries'.\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        '  "title": "پوری ریل یا کہانی کا جامع اردو عنوان",\n'
        '  "narration": "مکمل اردو کہانی شروع سے آخر تک",\n'
        '  "tags": ["اسلامی شارٹس", "Islamic Shorts", "Urdu Waqiat", "Storybox"],\n'
        '  "queries": ["desert sunset sky", "quiet night stars", "flowing river light", "open book pages"]\n'
        "}"
    )

    raw = _call_gemini(key, prompt, models)
    parsed = _extract_json(raw)
    if not parsed:
        raise RuntimeError("Gemini did not return valid JSON for Short story.")

    narration = str(parsed.get("narration") or "").strip()
    if len(narration.split()) < 60:
        raise RuntimeError("Generated Short narration is too short.")

    title = _clean_title(str(parsed.get("title") or ""), topic)

    raw_tags = parsed.get("tags")
    tags = [str(t).strip() for t in raw_tags if str(t).strip()][:15] if isinstance(raw_tags, list) else []
    if not tags:
        tags = ["اسلامی شارٹس", "Islamic Shorts", "Urdu Waqiat", "Storybox"]

    raw_q = parsed.get("queries")
    queries = [str(q).strip() for q in raw_q if str(q).strip()][:8] if isinstance(raw_q, list) else []
    if not queries:
        queries = ["desert sunset sky", "quiet night stars", "flowing river light", "open book pages"]

    print(f"Full-reel title: '{title}' ({len(narration.split())} words)")
    return {
        "id": f"short_{nonce}",
        "title": title,
        "narration": narration,
        "tags": tags,
        "queries": queries,
    }
