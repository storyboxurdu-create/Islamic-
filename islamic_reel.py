import asyncio
import json
import math
import os
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
FINAL_MP4 = os.path.abspath("final_islamic_short.mp4")
HISTORY_FILE = os.path.abspath("islamic_history.json")

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
  return (
      s.replace("\\", "\\\\")
      .replace(":", "\\:")
      .replace("'", "\\'")
      .replace("%", "\\%")
      .replace("[", "\\[")
      .replace("]", "\\]")
  )


def run_cmd(cmd: list[str]):
  res = subprocess.run(cmd, capture_output=True, text=True)
  if res.returncode != 0:
    print("CMD FAILED:", " ".join(cmd))
    print("STDERR:", res.stderr[-1500:])
    raise RuntimeError(f"Command failed with exit code {res.returncode}")


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
        url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=25
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


def _download_valid_img(url: str, out_path: str, timeout: int = 12) -> bool:
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

  cx, cy = w // 2, h // 2 + 8

  if any(k in low for k in ["money", "cash", "coin", "دولت", "پیسہ", "مال"]):
    draw.rectangle(
        [cx - 26, cy - 58, cx + 26, cy - 22],
        fill=(92, 178, 108),
        outline=(34, 88, 46),
        width=3,
    )
    draw.rectangle(
        [cx - 18, cy - 64, cx + 34, cy - 28],
        fill=(116, 198, 128),
        outline=(34, 88, 46),
        width=3,
    )
    draw.pieslice(
        [cx - 46, cy - 24, cx + 46, cy + 56],
        0,
        360,
        fill=(198, 152, 92),
        outline=(92, 60, 24),
        width=4,
    )
    draw.line(
        [(cx - 16, cy - 22), (cx + 16, cy - 22)], fill=(156, 36, 44), width=7
    )
    f = get_latin_font(38)
    draw.text((cx, cy + 18), "$", fill=(32, 128, 54), font=f, anchor="mm")

  elif any(k in low for k in ["family", "parent", "love", "رشتے", "ماں", "باپ", "ملاقات"]):
    people = [
        (-66, -24, 13, 28, (54, 124, 214)),
        (-34, -34, 15, 38, (224, 86, 122)),
        (-6, -16, 11, 22, (242, 164, 42)),
        (24, -34, 15, 38, (46, 158, 108)),
        (58, -22, 12, 26, (148, 92, 214)),
    ]
    for px, py, rad, bh, col in people:
      draw.ellipse(
          [cx + px - rad, cy + py - rad, cx + px + rad, cy + py + rad],
          fill=col,
          outline=(25, 30, 40),
          width=2,
      )
      top_b = cy + py + rad + 2
      draw.rounded_rectangle(
          [cx + px - rad - 3, top_b, cx + px + rad + 3, top_b + bh],
          radius=8,
          fill=col,
          outline=(25, 30, 40),
          width=2,
      )
      draw.line(
          [(cx + px - 5, top_b + bh), (cx + px - 5, top_b + bh + 14)],
          fill=(35, 42, 56),
          width=4,
      )
      draw.line(
          [(cx + px + 5, top_b + bh), (cx + px + 5, top_b + bh + 14)],
          fill=(35, 42, 56),
          width=4,
      )

  elif any(k in low for k in ["mistake", "error", "غلطیاں", "گناہ", "غلط"]):
    draw.ellipse(
        [cx - 14, cy - 52, cx + 14, cy - 24],
        fill=(214, 218, 226),
        outline=(55, 62, 75),
        width=3,
    )
    draw.rounded_rectangle(
        [cx - 18, cy - 22, cx + 18, cy + 24],
        radius=10,
        fill=(214, 218, 226),
        outline=(55, 62, 75),
        width=3,
    )
    draw.line(
        [(cx - 12, cy + 24), (cx - 10, cy + 54)],
        fill=(140, 146, 158),
        width=7,
    )
    draw.line(
        [(cx + 12, cy + 24), (cx + 10, cy + 54)],
        fill=(140, 146, 158),
        width=7,
    )
    draw.line(
        [(cx - 18, cy - 10), (cx - 42, cy - 26)],
        fill=(180, 185, 195),
        width=6,
    )
    draw.line(
        [(cx + 18, cy - 10), (cx + 42, cy - 26)],
        fill=(180, 185, 195),
        width=6,
    )
    draw.ellipse(
        [cx - 66, cy - 52, cx - 34, cy - 20],
        fill=(34, 178, 76),
        outline=(18, 104, 44),
        width=3,
    )
    draw.line(
        [(cx - 57, cy - 35), (cx - 51, cy - 28), (cx - 41, cy - 43)],
        fill=(255, 255, 255),
        width=4,
    )
    draw.ellipse(
        [cx + 34, cy - 52, cx + 66, cy - 20],
        fill=(224, 44, 56),
        outline=(132, 18, 28),
        width=3,
    )
    draw.line(
        [(cx + 43, cy - 43), (cx + 57, cy - 29)],
        fill=(255, 255, 255),
        width=4,
    )
    draw.line(
        [(cx + 57, cy - 43), (cx + 43, cy - 29)],
        fill=(255, 255, 255),
        width=4,
    )

  elif any(k in low for k in ["mosque", "masjid", "quran", "prayer", "توبہ", "مسجد", "نماز", "معافی"]):
    draw.pieslice(
        [cx - 48, cy - 38, cx + 48, cy + 38],
        180,
        360,
        fill=(24, 154, 102),
        outline=(16, 95, 62),
        width=3,
    )
    draw.rectangle(
        [cx - 48, cy - 2, cx + 48, cy + 36],
        fill=(246, 242, 230),
        outline=(120, 120, 120),
        width=2,
    )
    draw.polygon(
        [
            (cx - 24, cy + 44),
            (cx + 24, cy + 44),
            (cx + 12, cy + 20),
            (cx - 12, cy + 20),
        ],
        fill=(158, 104, 46),
    )
    draw.polygon(
        [
            (cx - 34, cy + 12),
            (cx, cy + 22),
            (cx, cy + 36),
            (cx - 34, cy + 26),
        ],
        fill=(255, 252, 240),
        outline=(90, 90, 90),
    )
    draw.polygon(
        [
            (cx + 34, cy + 12),
            (cx, cy + 22),
            (cx, cy + 36),
            (cx + 34, cy + 26),
        ],
        fill=(255, 252, 240),
        outline=(90, 90, 90),
    )

  elif any(k in low for k in ["sleep", "bed", "night", "سوتا", "نیند"]):
    draw.rectangle(
        [cx - 56, cy + 26, cx + 56, cy + 44], fill=(122, 76, 38)
    )
    draw.rectangle(
        [cx - 56, cy - 16, cx - 44, cy + 44], fill=(122, 76, 38)
    )
    draw.rounded_rectangle(
        [cx - 42, cy - 6, cx - 12, cy + 10],
        radius=4,
        fill=(248, 250, 255),
        outline=(160, 175, 195),
        width=2,
    )
    draw.rounded_rectangle(
        [cx - 44, cy + 6, cx + 54, cy + 28],
        radius=6,
        fill=(46, 114, 212),
    )
    draw.ellipse(
        [cx + 18, cy - 56, cx + 52, cy - 22], fill=(250, 204, 42)
    )
    draw.ellipse(
        [cx + 28, cy - 60, cx + 58, cy - 30], fill=(255, 255, 255)
    )

  elif any(k in low for k in ["football", "ball", "sport", "play", "کھیلتا", "کھیل"]):
    r = 44
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=(252, 252, 252),
        outline=(25, 28, 34),
        width=4,
    )
    draw.regular_polygon((cx, cy, 15), 5, fill=(28, 32, 38))
    for ang_deg in range(0, 360, 72):
      rad = math.radians(ang_deg)
      x1 = cx + 15 * math.cos(rad)
      y1 = cy + 15 * math.sin(rad)
      x2 = cx + (r - 2) * math.cos(rad)
      y2 = cy + (r - 2) * math.sin(rad)
      draw.line([(x1, y1), (x2, y2)], fill=(28, 32, 38), width=3)

  else:
    draw.ellipse(
        [cx - 40, cy - 40, cx + 40, cy + 40],
        fill=(244, 248, 252),
        outline=(28, 36, 52),
        width=4,
    )
    draw.ellipse(
        [cx - 12, cy - 12, cx + 12, cy + 12], fill=(28, 36, 52)
    )

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
      r = requests.get(url, timeout=10)
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
      fill=glow_color
