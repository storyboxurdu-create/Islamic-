import asyncio
import json
import math
import os
import random
import struct
import subprocess
from urllib.parse import quote
import wave
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import requests

try:
  import edge_tts

  HAS_TTS = True
except ImportError:
  HAS_TTS = False

W, H = 1080, 1920
FINAL_MP4 = "final_islamic_short.mp4"
HISTORY_FILE = "islamic_history.json"

FALLBACK_QUIZ = [
    {
        "question": "زندگی کی آخری ساعتوں میں\nانسان کو کیا یاد آتا ہے؟",
        "options": [
            ("A)", "money bag", "دولت"),
            ("B)", "family", "رشتے"),
            ("C)", "mistake", "غلطیاں"),
        ],
        "correct_index": 2,
        "answer_label": "درست جواب: غلطیاں",
        "question_speech": (
            "زندگی کی آخری ساعتوں میں انسان کو کیا یاد آتا ہے؟ "
            "دولت، رشتے، یا غلطیاں؟"
        ),
        "answer_speech": "درست جواب ہے: غلطیاں۔",
    },
    {
        "question": "اللہ اپنے بندے سے\nکب سب سے زیادہ خوش ہوتا ہے؟",
        "options": [
            ("A)", "sleep bed", "جب وہ سوتا ہے"),
            ("B)", "football", "جب وہ کھیلتا ہے"),
            ("C)", "mosque quran", "جب وہ توبہ کرتا ہے"),
        ],
        "correct_index": 2,
        "answer_label": "درست جواب: جب وہ توبہ کرتا ہے",
        "question_speech": (
            "اللہ اپنے بندے سے کب سب سے زیادہ خوش ہوتا ہے؟ "
            "جب وہ سوتا ہے، کھیلتا ہے، یا توبہ کرتا ہے؟"
        ),
        "answer_speech": "درست جواب ہے: جب وہ توبہ کرتا ہے۔",
    },
]


def discover_urdu_font() -> str:
  preferred = [
      "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
      "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
  ]
  for p in preferred:
    if os.path.exists(p):
      return p
  try:
    out = subprocess.check_output(
        ["fc-list", ":lang=ur", "file"], text=True, stderr=subprocess.DEVNULL
    )
    for line in out.splitlines():
      p = line.split(":")[0].strip()
      if p and os.path.exists(p) and p.lower().endswith((".ttf", ".otf")):
        return p
  except Exception:
    pass
  return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


URDU_FONT_FILE = discover_urdu_font()


def get_latin_font(size: int) -> ImageFont.FreeTypeFont:
  for p in [
      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
  ]:
    if os.path.exists(p):
      return ImageFont.truetype(p, size)
  return ImageFont.load_default()


def escape_drawtext(s: str) -> str:
  s = s.replace("\\", "\\\\")
  s = s.replace(":", "\\:")
  s = s.replace("'", "\\'")
  s = s.replace("%", "\\%")
  s = s.replace("[", "\\[")
  s = s.replace("]", "\\]")
  return s


def load_history() -> list[str]:
  if os.path.exists(HISTORY_FILE):
    try:
      with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list):
          return data
    except Exception:
      pass
  return []


def save_history(questions_used: list[str]) -> None:
  history = load_history()
  for q in questions_used:
    clean = " ".join(q.split())
    if clean and clean not in history:
      history.append(clean)
  with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(history[-200:], f, ensure_ascii=False, indent=2)


def generate_gemini_quiz() -> list[dict]:
  api_key = os.environ.get("GEMINI_API_KEY", "").strip()
  if not api_key:
    return FALLBACK_QUIZ

  used_questions = load_history()[-30:]
  avoid_text = "\n".join(f"- {q}" for q in used_questions)

  prompt = f"""
Generate 2 short, clear, engaging Islamic quiz questions in Urdu for a YouTube Short.
Rules:
- Use simple, natural Urdu (max 2 short lines per question, 1-3 Urdu words per option).
- Each option (A, B, C) must include 1-2 simple English search words for Pixabay (e.g. "money", "family", "mosque", "quran", "sleep").
- Include correct_index (0, 1, or 2), answer_label in Urdu, question_speech (complete Urdu question + options), and answer_speech (clear Urdu answer).
- Avoid repeating these previous questions:
{avoid_text}

Return ONLY valid JSON list of 2 items:
[
  {{
    "question": "آسان اردو سوال سطر 1\\nسطر 2",
    "options": [
      ["A)", "simple word 1", "آسان آپشن 1"],
      ["B)", "simple word 2", "آسان آپشن 2"],
      ["C)", "simple word 3", "آسان آپشن 3"]
    ],
    "correct_index": 1,
    "answer_label": "درست جواب: آسان آپشن 2",
    "question_speech": "مکمل اردو سوال اور آپشنز؟",
    "answer_speech": "درست جواب ہے: آسان آپشن 2۔"
  }}
]
"""
  url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
  try:
    res = requests.post(
        url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30
    )
    res.raise_for_status()
    txt = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    if txt.startswith("```"):
      txt = txt.strip("`")
      if txt.startswith("json"):
        txt = txt[4:]
      txt = txt.strip()
    data = json.loads(txt)
    if isinstance(data, list) and len(data) >= 2:
      out = []
      for item in data[:2]:
        opts = [
            (str(o[0]), str(o[1]), str(o[2])) for o in item.get("options", [])[:3]
        ]
        if len(opts) == 3 and item.get("question"):
          out.append({
              "question": str(item["question"]),
              "options": opts,
              "correct_index": int(item.get("correct_index", 0)) % 3,
              "answer_label": str(item.get("answer_label", "")),
              "question_speech": str(
                  item.get("question_speech", item["question"])
              ),
              "answer_speech": str(
                  item.get("answer_speech", item.get("answer_label", ""))
              ),
          })
      if len(out) == 2:
        return out
  except Exception as e:
    print("Gemini error, using fallback:", e)
  return FALLBACK_QUIZ


def _download_valid_img(url: str, out_path: str, timeout: int = 15) -> bool:
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
      )
  }
  r = requests.get(url, headers=headers, timeout=timeout)
  r.raise_for_status()
  if len(r.content) < 1500:
    return False
  with open(out_path, "wb") as f:
    f.write(r.content)
  with Image.open(out_path) as im:
    im.verify()
  return True


def build_clean_sticker_thumb(
    query: str, urdu_label: str, out_path: str, w: int = 260, h: int = 190
) -> str:
  low = f"{query} {urdu_label}".lower()
  img = Image.new("RGB", (w, h), (255, 255, 255))
  draw = ImageDraw.Draw(img)

  cx, cy = w // 2, h // 2
  if any(k in low for k in ["money", "cash", "coin", "دولت", "پیسہ", "مال"]):
    draw.rounded_rectangle(
        [cx - 52, cy - 22, cx + 52, cy + 48],
        radius=20,
        fill=(186, 134, 72),
        outline=(95, 62, 25),
        width=3,
    )
    draw.rounded_rectangle(
        [cx - 32, cy - 38, cx + 32, cy - 16],
        radius=8,
        fill=(158, 108, 52),
        outline=(95, 62, 25),
        width=3,
    )
    f = get_latin_font(44)
    draw.text((cx, cy + 14), "$", fill=(255, 235, 130), font=f, anchor="mm")
  elif any(k in low for k in ["family", "parent", "love", "رشتے", "ماں", "باپ", "ملاقات"]):
    for dx, r_h, b_h, col in [
        (-44, 17, 42, (52, 122, 212)),
        (44, 17, 42, (224, 82, 118)),
        (0, 13, 30, (242, 158, 42)),
    ]:
      hy = cy - 24 + (8 if r_h == 13 else 0)
      draw.ellipse([cx + dx - r_h, hy - r_h, cx + dx + r_h, hy + r_h], fill=col)
      by1 = hy + r_h + 4
      draw.rounded_rectangle(
          [cx + dx - r_h - 3, by1, cx + dx + r_h + 3, by1 + b_h],
          radius=12,
          fill=col,
      )
  elif any(k in low for k in ["mistake", "error", "غلطیاں", "گناہ", "غلط"]):
    draw.ellipse(
        [cx - 46, cy - 46, cx + 46, cy + 46],
        fill=(220, 44, 56),
        outline=(130, 18, 28),
        width=3,
    )
    draw.line([(cx - 20, cy - 20), (cx + 20, cy + 20)], fill=(255, 255, 255), width=8)
    draw.line([(cx + 20, cy - 20), (cx - 20, cy + 20)], fill=(255, 255, 255), width=8)
  elif any(k in low for k in ["mosque", "masjid", "quran", "prayer", "توبہ", "مسجد", "نماز", "معافی"]):
    draw.pieslice([cx - 52, cy - 42, cx + 52, cy + 52], 180, 360, fill=(22, 145, 96))
    draw.rectangle([cx - 52, cy + 4, cx + 52, cy + 44], fill=(242, 238, 224), outline=(140, 135, 120), width=2)
    draw.ellipse([cx - 9, cy - 58, cx + 9, cy - 40], fill=(245, 198, 42))
  elif any(k in low for k in ["sleep", "bed", "night", "سوتا", "نیند"]):
    draw.rounded_rectangle([cx - 54, cy - 10, cx + 54, cy + 40], radius=16, fill=(72, 124, 212))
    draw.ellipse([cx - 22, cy - 48, cx + 22, cy - 4], fill=(250, 204, 42))
    draw.ellipse([cx - 6, cy - 52, cx + 32, cy - 14], fill=(255, 255, 255))
  else:
    draw.ellipse(
        [cx - 44, cy - 44, cx + 44, cy + 44],
        fill=(248, 250, 252),
        outline=(30, 36, 48),
        width=4,
    )
    draw.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=(30, 36, 48))

  img.save(out_path)
  return out_path


def fetch_option_photo(query: str, urdu_label: str, out_path: str) -> str:
  api_key = os.environ.get("PIXABAY_API_KEY", "").strip()
  words = [w for w in (query or "").split() if w.isalpha()]
  short_q = " ".join(words[:2]) if words else " ".join((query or "").split()[:2])

  if api_key and short_q:
    try:
      url = (
          f"[https://pixabay.com/api/?key=](https://pixabay.com/api/?key=){api_key}"
          f"&q={quote(short_q)}&image_type=photo&safesearch=true&per_page=5"
      )
      r = requests.get(url, timeout=12)
      r.raise_for_status()
      hits = r.json().get("hits", [])
      for hit in hits:
        img_url = hit.get("webformatURL") or hit.get("largeImageURL")
        if img_url and _download_valid_img(img_url, out_path):
          return out_path
    except Exception as e:
      print("Pixabay skip:", short_q, e)

  return build_clean_sticker_thumb(query, urdu_label, out_path)


def fit_photo(path: str, w: int, h: int) -> Image.Image:
  im = Image.open(path).convert("RGB")
  scale = max(w / im.width, h / im.height)
  nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
  im = im.resize((nw, nh), Image.Resampling.LANCZOS)
  x0 = max(0, (nw - w) // 2)
  y0 = max(0, (nh - h) // 2)
  return im.crop((x0, y0, x0 + w, y0 + h))


def make_smooth_background() -> Image.Image:
  base = Image.new("RGB", (W, H), (22, 152, 110))
  draw = ImageDraw.Draw(base)
  for y in range(H):
    t = y / H
    r = int(20 + 14 * t)
    g = int(162 - 48 * t)
    b = int(116 - 28 * t)
    draw.line([(0, y), (W, y)], fill=(r, g, b))

  glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
  gdraw = ImageDraw.Draw(glow)
  gdraw.ellipse([90, 140, 990, 740], fill=(135, 255, 205, 70))
  glow = glow.filter(ImageFilter.GaussianBlur(70))
  return Image.alpha_composite(base.convert("RGBA"), glow).convert("RGB")


def draw_smooth_card(
    canvas_rgba: Image.Image,
    box: list[int],
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    glow_color: tuple[int, int, int, int],
    width: int = 6,
):
  glow = Image.new("RGBA", canvas_rgba.size, (0, 0, 0, 0))
  gdraw = ImageDraw.Draw(glow)
  gdraw.rounded_rectangle(
      [box[0] - 8, box[1] - 8, box[2] + 8, box[3] + 8],
      radius=radius + 6,
      fill=glow_color,
  )
  glow = glow.filter(ImageFilter.GaussianBlur(14))
  canvas_rgba.alpha_composite(glow)

  layer = Image.new("RGBA", canvas_rgba.size, (0, 0, 0, 0))
  ldraw = ImageDraw.Draw(layer)
  ldraw.rounded_rectangle(
      box, radius=radius, fill=fill, outline=outline, width=width
  )
  canvas_rgba.alpha_composite(layer)


def render_base_card_png(
    item: dict,
    thumb_paths: list[str],
    out_png: str,
    timer_num: int |
