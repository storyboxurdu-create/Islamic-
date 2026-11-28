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
      .replace("[", "\\[") .replace("]", "\\]")
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
    # Stacked cash bills at top of money bag
    for bx_off, by_off, col in [
        (-20, -58, (76, 162, 92)),
        (6, -64, (98, 184, 114)),
        (-6, -50, (122, 204, 136)),
    ]:
      draw.rounded_rectangle(
          [cx + bx_off, cy + by_off, cx + bx_off + 36, cy + by_off + 24],
          radius=4,
          fill=col,
          outline=(26, 74, 38),
          width=2,
      )
    # Shaded brown money sack + red tie ribbon + $ emblem
    draw.ellipse(
        [cx - 46, cy - 22, cx + 46, cy + 56],
        fill=(188, 134, 72),
        outline=(86, 52, 20),
        width=4,
    )
    draw.ellipse(
        [cx - 32, cy - 12, cx + 22, cy + 44],
        fill=(212, 160, 96),
    )
    draw.rounded_rectangle(
        [cx - 22, cy - 28, cx + 22, cy - 14],
        radius=6,
        fill=(166, 36, 44),
        outline=(86, 20, 24),
        width=2,
    )
    f = get_latin_font(40)
    draw.text((cx, cy + 18), "$", fill=(54, 34, 14), font=f, anchor="mm")

  elif any(k in low for k in ["family", "parent", "love", "رشتے", "ماں", "باپ", "ملاقات"]):
    # Multi-person shaded family group with soft floor shadow
    draw.ellipse([cx - 88, cy + 48, cx + 88, cy + 62], fill=(224, 228, 234))
    members = [
        (-70, -18, 12, 26, (66, 134, 224), (42, 62, 110)),
        (-42, -32, 14, 34, (228, 92, 128), (58, 72, 128)),
        (-14, -12, 10, 20, (245, 174, 46), (52, 88, 152)),
        (14, -32, 14, 34, (54, 168, 116), (48, 66, 114)),
        (42, -20, 12, 26, (156, 98, 222), (62, 68, 124)),
        (68, -14, 11, 22, (236, 126, 52), (56, 78, 136)),
    ]
    for mx, my, rad, bh, shirt_col, pant_col in members:
      draw.ellipse(
          [cx + mx - rad, cy + my - rad, cx + mx + rad, cy + my + rad],
          fill=(242, 194, 156),
          outline=(42, 34, 28),
          width=2,
      )
      draw.pieslice(
          [cx + mx - rad, cy + my - rad - 2, cx + mx + rad, cy + my + 2],
          180,
          360,
          fill=(52, 36, 28),
      )
      s_top = cy + my + rad + 1
      draw.rounded_rectangle(
          [cx + mx - rad - 2, s_top, cx + mx + rad + 2, s_top + bh],
          radius=7,
          fill=shirt_col,
          outline=(34, 38, 46),
          width=2,
      )
      p_top = s_top + bh - 2
      draw.rectangle(
          [cx + mx - rad + 1, p_top, cx + mx - 1, p_top + 13], fill=pant_col
      )
      draw.rectangle(
          [cx + mx + 1, p_top, cx + mx + rad - 1, p_top + 13], fill=pant_col
      )

  elif any(k in low for k in ["mistake", "error", "غلطیاں", "گناہ", "غلط"]):
    # Shaded 3D-style figure holding green check and red cross badges
    draw.ellipse([cx - 58, cy + 46, cx + 58, cy + 60], fill=(224, 228, 234))
    draw.ellipse(
        [cx - 16, cy - 52, cx + 16, cy - 20],
        fill=(226, 230, 238),
        outline=(68, 74, 86),
        width=3,
    )
    draw.rounded_rectangle(
        [cx - 20, cy - 18, cx + 20, cy + 22],
        radius=10,
        fill=(226, 230, 238),
        outline=(68, 74, 86),
        width=3,
    )
    draw.rounded_rectangle(
        [cx - 15, cy + 20, cx - 3, cy + 52],
        radius=5,
        fill=(198, 204, 214),
        outline=(68, 74, 86),
        width=2,
    )
    draw.rounded_rectangle(
        [cx + 3, cy + 20, cx + 15, cy + 52],
        radius=5,
        fill=(198, 204, 214),
        outline=(68, 74, 86),
        width=2,
    )
    draw.line(
        [(cx - 18, cy - 8), (cx - 42, cy - 24)],
        fill=(176, 182, 192),
        width=7,
    )
    draw.line(
        [(cx + 18, cy - 8), (cx + 42, cy - 24)],
        fill=(176, 182, 192),
        width=7,
    )
    # Green check circle
    draw.ellipse(
        [cx - 70, cy - 56, cx - 32, cy - 18],
        fill=(38, 186, 82),
        outline=(16, 96, 40),
        width=3,
    )
    draw.line(
        [(cx - 60, cy - 36), (cx - 53, cy - 28), (cx - 41, cy - 45)],
        fill=(255, 255, 255),
        width=5,
    )
    # Red cross circle
    draw.ellipse(
        [cx + 32, cy - 56, cx + 70, cy - 18],
        fill=(228, 46, 58),
        outline=(126, 16, 26),
        width=3,
    )
    draw.line(
        [(cx + 42, cy - 46), (cx + 60, cy - 28)],
        fill=(255, 255, 255),
        width=5,
    )
    draw.line(
        [(cx + 60, cy - 46), (cx + 42, cy - 28)],
        fill=(255, 255, 255),
        width=5,
    )

  elif any(k in low for k in ["forgive", "dua", "pray", "sorry", "معافی", "دعا", "توبہ"]):
    # Raised dua / forgiveness hands outline + warm yellow fill
    draw.rounded_rectangle(
        [cx - 34, cy - 28, cx - 10, cy + 44],
        radius=10,
        fill=(252, 224, 92),
        outline=(24, 28, 36),
        width=4,
    )
    draw.rounded_rectangle(
        [cx + 10, cy - 28, cx + 34, cy + 44],
        radius=10,
        fill=(252, 224, 92),
        outline=(24, 28, 36),
        width=4,
    )
    draw.rounded_rectangle(
        [cx - 44, cy + 12, cx - 18, cy + 48],
        radius=10,
        fill=(252, 224, 92),
        outline=(24, 28, 36),
        width=4,
    )
    draw.rounded_rectangle(
        [cx + 18, cy + 12, cx + 44, cy + 48],
        radius=10,
        fill=(252, 224, 92),
        outline=(24, 28, 36),
        width=4,
    )

  elif any(k in low for k in ["mosque", "masjid", "quran", "prayer", "مسجد", "نماز"]):
    # Dome + open book on stand
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
        [cx - 42, cy - 42, cx + 42, cy + 42],
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
    timer_num: int | None = None,
    show_answer: bool = False,
) -> str:
  bg = make_smooth_background().convert("RGBA")
  badge_font = get_latin_font(44)
  timer_font = get_latin_font(60)

  draw_smooth_card(
      bg,
      [54, 175, 1026, 595],
      radius=38,
      fill=(255, 255, 255, 255),
      outline=(15, 20, 28, 255),
      glow_color=(135, 255, 200, 95),
      width=6,
  )

  if timer_num is not None and not show_answer:
    bx1, by1, bx2, by2 = 85, 622, 865, 666
    draw_smooth_card(
        bg,
        [bx1, by1, bx2, by2],
        radius=18,
        fill=(225, 234, 244, 255),
        outline=(20, 25, 35, 255),
        glow_color=(255, 220, 90, 90),
        width=4,
    )
    frac = max(0.05, min(1.0, timer_num / 5.0))
    fw = int((bx2 - bx1 - 12) * frac)
    bdraw = ImageDraw.Draw(bg)
    bdraw.rounded_rectangle(
        [bx1 + 6, by1 + 6, bx1 + 6 + fw, by2 - 6],
        radius=12,
        fill=(235, 25, 115),
    )

  start_y = 690
  row_h = 200
  gap = 22
  correct_idx = item.get("correct_index", 0)

  for idx in range(3):
    y1 = start_y + idx * (row_h + gap)
    y2 = y1 + row_h
    is_win = show_answer and (idx == correct_idx)

    fill_col = (255, 244, 145, 255) if is_win else (255, 255, 255, 255)
    out_col = (18, 145, 62, 255) if is_win else (15, 20, 28, 255)
    glow_col = (255, 225, 70, 165) if is_win else (255, 245, 180, 75)
    b_w = 8 if is_win else 6

    draw_smooth_card(
        bg,
        [54, y1, 895, y2],
        radius=32,
        fill=fill_col,
        outline=out_col,
        glow_color=glow_col,
        width=b_w,
    )

    row_draw = ImageDraw.Draw(bg)
    photo = fit_photo(thumb_paths[idx], 230, row_h - 28)
    bg.paste(photo, (82, y1 + 14))

    b_letter = ["A", "B", "C"][idx]
    row_draw.rounded_rectangle(
        [82, y1 + 14, 130, y1 + 60],
        radius=12,
        fill=(18, 135, 62) if is_win else (20, 28, 45),
    )
    row_draw.text(
        (106, y1 + 37),
        b_letter,
        fill=(255, 255, 255),
        font=badge_font,
        anchor="mm",
    )

  if timer_num is not None and not show_answer:
    draw_smooth_card(
        bg,
        [385, 1340, 565, 1445],
        radius=28,
        fill=(18, 24, 36, 255),
        outline=(255, 215, 70, 255),
        glow_color=(255, 215, 70, 140),
        width=5,
    )
    fdraw = ImageDraw.Draw(bg)
    fdraw.text(
        (475, 1392),
        str(timer_num),
        fill=(255, 228, 85, 255),
        font=timer_font,
        anchor="mm",
    )

  if show_answer and item.get("answer_label"):
    draw_smooth_card(
        bg,
        [54, 1340, 895, 1445],
        radius=28,
        fill=(14, 120, 56, 255),
        outline=(255, 255, 255, 255),
        glow_color=(55, 245, 125, 155),
        width=6,
    )

  bg.convert("RGB").save(out_png)
  return out_png


def render_slot_clip_with_ffmpeg(
    base_png: str,
    item: dict,
    dur: float,
    out_mp4: str,
    show_answer: bool = False,
):
  filters = [f"scale={W}:{H},fps=30,format=yuv420p"]
  font_arg = escape_drawtext(URDU_FONT_FILE)

  q_lines = [ln.strip() for ln in item["question"].split("\n") if ln.strip()]
  if len(q_lines) == 1:
    q_positions = [(q_lines[0], 385)]
  else:
    q_positions = [(q_lines[0], 335), (q_lines[1], 435)]

  for q_line, y_pos in q_positions:
    filters.append(
        f"drawtext=fontfile='{font_arg}':text='{escape_drawtext(q_line)}':"
        f"fontcolor=#0A0C10:fontsize=72:x=(w-text_w)/2:y={y_pos}-text_h/2"
    )

  start_y = 690
  row_h = 200
  gap = 22
  for idx, (_, _, label) in enumerate(item["options"][:3]):
    y_center = start_y + idx * (row_h + gap) + row_h // 2
    filters.append(
        f"drawtext=fontfile='{font_arg}':text='{escape_drawtext(label.strip())}':"
        f"fontcolor=#0A0C10:fontsize=58:x=865-text_w:y={y_center}-text_h/2"
    )

  if show_answer and item.get("answer_label"):
    filters.append(
        f"drawtext=fontfile='{font_arg}':text='{escape_drawtext(item['answer_label'].strip())}':"
        f"fontcolor=#FFFFFF:fontsize=46:x=(w-text_w)/2:y=1392-text_h/2"
    )

  vf_expr = ",".join(filters)
  run_cmd([
      "ffmpeg",
      "-y",
      "-loop",
      "1",
      "-i",
      base_png,
      "-t",
      f"{dur:.3f}",
      "-vf",
      vf_expr,
      "-c:v",
      "libx264",
      "-preset",
      "fast",
      "-crf",
      "22",
      out_mp4,
  ])


async def _tts_save(text: str, out_mp3: str, rate: str = "+0%", pitch: str = "-2Hz"):
  for voice in ["ur-PK-AsadNeural", "ur-PK-UzmaNeural"]:
    try:
      comm = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
      await asyncio.wait_for(comm.save(out_mp3), timeout=20)
      if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 400:
        return
    except Exception as e:
      print("TTS retry:", voice, e)


def _mp3_to_mono_samples(
    mp3_path: str, sr: int, work_dir: str, tag: str
) -> list[float]:
  if not (
      HAS_TTS and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 400
  ):
    return []
  wav_tmp = os.path.join(work_dir, f"{tag}_tmp.wav")
  try:
    run_cmd([
        "ffmpeg",
        "-y",
        "-i",
        mp3_path,
        "-ar",
        str(sr),
        "-ac",
        "1",
        "-f",
        "wav",
        wav_tmp,
    ])
    with wave.open(wav_tmp, "rb") as wf:
      n = wf.getnframes()
      raw = struct.unpack(f"<{n}h", wf.readframes(n))
      return [(x / 32768.0) * 0.96 for x in raw]
  except Exception as e:
    print("WAV decode error:", tag, e)
    return []


def build_dynamic_question_track(
    item: dict, out_wav: str, work_dir: str
) -> tuple[str, float, float, float]:
  sr = 44100
  base_name = os.path.basename(out_wav)

  q_speech = item.get("question_speech", "")
  a_speech = item.get("answer_speech", item.get("answer_label", ""))

  q_samples: list[float] = []
  if HAS_TTS and q_speech.strip():
    q_mp3 = os.path.join(work_dir, f"{base_name}_q.mp3")
    asyncio.run(_tts_save(q_speech, q_mp3, rate="+0%", pitch="-2Hz"))
    q_samples = _mp3_to_mono_samples(q_mp3, sr, work_dir, f"{base_name}_q")

  intro_dur = max(3.0, len(q_samples) / sr + 0.25)

  a_samples: list[float] = []
  if HAS_TTS and a_speech.strip():
    a_mp3 = os.path.join(work_dir, f"{base_name}_a.mp3")
    asyncio.run(_tts_save(a_speech, a_mp3, rate="+0%", pitch="-2Hz"))
    a_samples = _mp3_to_mono_samples(a_mp3, sr, work_dir, f"{base_name}_a")

  buzz_dur = 0.8
  ans_dur = max(2.2, buzz_dur + len(a_samples) / sr + 0.35)
  timer_dur = 5.0
  total_dur = intro_dur + timer_dur + ans_dur

  total_n = int(total_dur * sr)
  samples = [0.0] * total_n

  for i, val in enumerate(q_samples):
    if i < total_n:
      samples[i] += val

  timer_start = intro_dur
  for sec_i in range(5):
    t_s = timer_start + sec_i * 1.0
    s_i = int(t_s * sr)
    tick_len = int(0.06 * sr)
    for k in range(tick_len):
      pos = s_i + k
      if pos < total_n:
        t_rel = k / sr
        env = math.exp(-k / (0.016 * sr))
        snap = 0.34 * env * math.sin(2 * math.pi * 1650 * t_rel)
        body = 0.16 * env * math.sin(2 * math.pi * 680 * t_rel)
        samples[pos] += snap + body

  ans_start = intro_dur + timer_dur
  b_start_i = int(ans_start * sr)
  b_len = int(buzz_dur * sr)
  for k in range(b_len):
    pos = b_start_i + k
    if pos < total_n:
      t_rel = k / sr
      fade_in = min(1.0, k / (0.015 * sr))
      fade_out = min(1.0, (b_len - k) / (0.06 * sr))
      tone = 0.28 * math.sin(2 * math.pi * 660 * t_rel) + 0.11 * math.sin(
          2 * math.pi * 1320 * t_rel
      )
      samples[pos] += tone * fade_in * fade_out

  speech_a_start_i = int((ans_start + buzz_dur + 0.1) * sr)
  for i, val in enumerate(a_samples):
    pos = speech_a_start_i + i
    if pos < total_n:
      samples[pos] += val

  with wave.open(out_wav, "wb") as out_wf:
    out_wf.setnchannels(2)
    out_wf.setsampwidth(2)
    out_wf.setframerate(sr)
    packed = bytearray()
    for s in samples:
      clamped = max(-0.98, min(0.98, s))
      iv = int(clamped * 32767)
      rec = struct.pack("<hh", iv, iv)
      packed.extend(rec)
    out_wf.writeframes(packed)

  return out_wav, intro_dur, timer_dur, ans_dur


def main():
  work_dir = os.path.abspath("quiz_build")
  os.makedirs(work_dir, exist_ok=True)
  print("Starting islamic_reel.py ->", FINAL_MP4)
  print("Using Urdu font:", URDU_FONT_FILE)

  quiz_items = generate_gemini_quiz()
  print("Loaded quiz items:", len(quiz_items))

  video_parts = []
  audio_parts = []
  total_video_sec = 0.0

  for q_idx, item in enumerate(quiz_items[:2]):
    print(f"Building Q{q_idx+1}...")
    thumb_paths = []
    for o_idx, (_, photo_query, urdu_label) in enumerate(item["options"][:3]):
      p_file = os.path.join(work_dir, f"q{q_idx+1}_opt{o_idx+1}.jpg")
      thumb_paths.append(fetch_option_photo(photo_query, urdu_label, p_file))

    wav_p = os.path.join(work_dir, f"q{q_idx+1}_full.wav")
    _, intro_dur, timer_dur, ans_dur = build_dynamic_question_track(
        item, wav_p, work_dir
    )
    audio_parts.append(wav_p)
    total_video_sec += intro_dur + timer_dur + ans_dur

    slots = [
        ("q_intro", intro_dur, None, False),
        ("t_5", 1.0, 5, False),
        ("t_4", 1.0, 4, False),
        ("t_3", 1.0, 3, False),
        ("t_2", 1.0, 2, False),
        ("t_1", 1.0, 1, False),
        ("t_ans", ans_dur, None, True),
    ]

    for tag, dur, t_num, is_ans in slots:
      base_png = os.path.join(work_dir, f"q{q_idx+1}_{tag}_base.png")
      mp4_p = os.path.join(work_dir, f"q{q_idx+1}_{tag}.mp4")
      render_base_card_png(
          item, thumb_paths, base_png, timer_num=t_num, show_answer=is_ans
      )
      render_slot_clip_with_ffmpeg(
          base_png, item, dur, mp4_p, show_answer=is_ans
      )
      video_parts.append(mp4_p)

  v_list = os.path.join(work_dir, "v_list.txt")
  with open(v_list, "w", encoding="utf-8") as f:
    for vp in video_parts:
      f.write(f"file '{vp}'\n")

  a_list = os.path.join(work_dir, "a_list.txt")
  with open(a_list, "w", encoding="utf-8") as f:
    for ap in audio_parts:
      f.write(f"file '{ap}'\n")

  merged_v = os.path.join(work_dir, "merged_v.mp4")
  merged_a = os.path.join(work_dir, "merged_a.wav")

  run_cmd([
      "ffmpeg",
      "-y",
      "-f",
      "concat",
      "-safe",
      "0",
      "-i",
      v_list,
      "-c",
      "copy",
      merged_v,
  ])
  run_cmd([
      "ffmpeg",
      "-y",
      "-f",
      "concat",
      "-safe",
      "0",
      "-i",
      a_list,
      "-c",
      "copy",
      merged_a,
  ])

  final_dur = min(59.0, total_video_sec)
  run_cmd([
      "ffmpeg",
      "-y",
      "-i",
      merged_v,
      "-i",
      merged_a,
      "-t",
      f"{final_dur:.2f}",
      "-map",
      "0:v",
      "-map",
      "1:a",
      "-c:v",
      "copy",
      "-c:a",
      "aac",
      "-b:a",
      "128k",
      FINAL_MP4,
  ])

  save_history([x["question"] for x in quiz_items[:2]])
  print(
      f"Successfully built {FINAL_MP4} ({final_dur:.1f}s,"
      f" {os.path.getsize(FINAL_MP4)} bytes)"
  )


if __name__ == "__main__":
  main()
