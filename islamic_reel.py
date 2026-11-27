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
  import arabic_reshaper

  HAS_RESHAPER = True
except ImportError:
  HAS_RESHAPER = False

try:
  from bidi.algorithm import get_display

  HAS_BIDI = True
except ImportError:
  HAS_BIDI = False

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
            ("A)", "money bag cash coins", "دولت"),
            ("B)", "family parents children", "رشتے"),
            ("C)", "mistake regret error", "غلطیاں"),
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
            ("A)", "sleeping bed night", "جب وہ سوتا ہے"),
            ("B)", "football soccer field", "جب وہ کھیلتا ہے"),
            ("C)", "quran prayer mosque", "جب وہ توبہ کرتا ہے"),
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


def discover_urdu_font() -> str | None:
  candidates = [
      "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
      "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
  ]
  for p in candidates:
    if os.path.exists(p):
      return p
  try:
    out = subprocess.check_output(
        ["fc-list", ":lang=ur", "file"], text=True, stderr=subprocess.DEVNULL
    )
    files = [
        line.split(":")[0].strip()
        for line in out.splitlines()
        if line.strip().lower().endswith((".ttf", ".otf"))
    ]
    for f in files:
      if "bold" in f.lower():
        return f
    if files:
      return files[0]
  except Exception:
    pass
  return None


URDU_FONT_FILE = discover_urdu_font()


def get_urdu_font(size: int) -> ImageFont.FreeTypeFont:
  if URDU_FONT_FILE and os.path.exists(URDU_FONT_FILE):
    return ImageFont.truetype(URDU_FONT_FILE, size)
  return ImageFont.load_default()


def get_latin_font(size: int) -> ImageFont.FreeTypeFont:
  for p in [
      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
  ]:
    if os.path.exists(p):
      return ImageFont.truetype(p, size)
  return ImageFont.load_default()


def urdu_text(text: str) -> str:
  """
    Clean Urdu shaping for PIL: reshapes Arabic/Urdu characters and applies bidi display
    without reversing character/word order manually.
    """
  if not text:
    return ""
  out = []
  for raw in text.split("\n"):
    line = raw.strip()
    if not line:
      out.append("")
      continue
    if HAS_RESHAPER and HAS_BIDI:
      out.append(get_display(arabic_reshaper.reshape(line)))
    elif HAS_RESHAPER:
      out.append(arabic_reshaper.reshape(line))
    else:
      out.append(line)
  return "\n".join(out)


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
- Use simple, natural Urdu (max 2 short lines per question, 1-4 Urdu words per option).
- Each option (A, B, C) must include a clear 2-4 word English keyword for photo/sticker matching.
- Include correct_index (0, 1, or 2), answer_label in Urdu, question_speech (complete Urdu question + options), and answer_speech (clear Urdu answer).
- Avoid repeating these previous questions:
{avoid_text}

Return ONLY valid JSON list of 2 items:
[
  {{
    "question": "آسان اردو سوال سطر 1\\nسطر 2",
    "options": [
      ["A)", "keyword 1", "آسان آپشن 1"],
      ["B)", "keyword 2", "آسان آپشن 2"],
      ["C)", "keyword 3", "آسان آپشن 3"]
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


def build_realistic_sticker(
    query: str, urdu_label: str, out_path: str, w: int = 260, h: int = 190
) -> str:
  """
    Creates a clean glossy sticker-style visual matching the topic when real photos are unavailable.
    """
  low = f"{query} {urdu_label}".lower()
  img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
  draw = ImageDraw.Draw(img)

  # Sticker white border backing
  pad = 12
  draw.rounded_rectangle(
      [pad, pad, w - pad, h - pad],
      radius=28,
      fill=(255, 255, 255, 255),
      outline=(210, 218, 228, 255),
      width=4,
  )

  cx, cy = w // 2, h // 2
  if any(k in low for k in ["money", "cash", "coin", "دولت", "پیسہ", "مال"]):
    # Glossy green money pouch sticker + gold coin
    draw.rounded_rectangle(
        [cx - 56, cy - 22, cx + 56, cy + 44],
        radius=16,
        fill=(34, 152, 78, 255),
        outline=(20, 95, 48, 255),
        width=3,
    )
    draw.polygon(
        [(cx - 24, cy - 22), (cx + 24, cy - 22), (cx + 36, cy - 42), (cx - 36, cy - 42)],
        fill=(46, 175, 92, 255),
    )
    draw.ellipse(
        [cx - 20, cy - 8, cx + 20, cy + 32],
        fill=(255, 212, 58, 255),
        outline=(185, 135, 15, 255),
        width=3,
    )
  elif any(k in low for k in ["family", "parent", "love", "رشتے", "ماں", "باپ", "بچے"]):
    # Warm 3-person family sticker (parent left, parent right, child center)
    for dx, r_head, body_h, col in [
        (-42, 18, 42, (58, 128, 215, 255)),
        (42, 18, 42, (224, 86, 122, 255)),
        (0, 14, 30, (245, 166, 48, 255)),
    ]:
      hy = cy - 24 + (8 if r_head == 14 else 0)
      draw.ellipse(
          [cx + dx - r_head, hy - r_head, cx + dx + r_head, hy + r_head],
          fill=col,
      )
      by1 = hy + r_head + 4
      draw.rounded_rectangle(
          [cx + dx - r_head - 4, by1, cx + dx + r_head + 4, by1 + body_h],
          radius=14,
          fill=col,
      )
  elif any(k in low for k in ["mistake", "regret", "error", "غلطیاں", "گناہ", "غلط"]):
    # Bold glossy red X sticker badge
    draw.ellipse(
        [cx - 46, cy - 46, cx + 46, cy + 46],
        fill=(224, 48, 60, 255),
        outline=(140, 20, 30, 255),
        width=4,
    )
    draw.line(
        [(cx - 20, cy - 20), (cx + 20, cy + 20)],
        fill=(255, 255, 255, 255),
        width=9,
    )
    draw.line(
        [(cx + 20, cy - 20), (cx - 20, cy + 20)],
        fill=(255, 255, 255, 255),
        width=9,
    )
  elif any(k in low for k in ["mosque", "masjid", "quran", "prayer", "توبہ", "مسجد", "نماز", "قرآن"]):
    # Glossy emerald dome + gold crescent sticker
    draw.pieslice(
        [cx - 48, cy - 46, cx + 48, cy + 50],
        180,
        360,
        fill=(22, 145, 98, 255),
    )
    draw.rounded_rectangle(
        [cx - 48, cy + 2, cx + 48, cy + 44],
        radius=10,
        fill=(245, 242, 232, 255),
        outline=(160, 155, 140, 255),
        width=2,
    )
    draw.ellipse(
        [cx - 10, cy - 62, cx + 10, cy - 42],
        fill=(255, 208, 52, 255),
    )
  elif any(k in low for k in ["sleep", "bed", "night", "سوتا", "نیند"]):
    # Crescent moon + pillow sticker
    draw.ellipse([cx - 32, cy - 48, cx + 32, cy + 16], fill=(255, 210, 55, 255))
    draw.ellipse([cx - 14, cy - 52, cx + 42, cy + 4], fill=(255, 255, 255, 255))
    draw.rounded_rectangle(
        [cx - 46, cy + 16, cx + 46, cy + 44],
        radius=12,
        fill=(88, 128, 215, 255),
    )
  else:
    # Sports ball sticker
    draw.ellipse(
        [cx - 44, cy - 44, cx + 44, cy + 44],
        fill=(248, 250, 252, 255),
        outline=(35, 42, 55, 255),
        width=4,
    )
    draw.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=(35, 42, 55, 255))

  # Subtle white sticker drop shadow
  bg = Image.new("RGBA", (w, h), (255, 255, 255, 255))
  bg.alpha_composite(img)
  bg.convert("RGB").save(out_path)
  return out_path


def fetch_option_photo(query: str, urdu_label: str, out_path: str) -> str:
  api_key = os.environ.get("PIXABAY_API_KEY", "").strip()
  clean_q = " ".join((query or "").split()[:4])

  if api_key and clean_q:
    try:
      url = (
          f"[https://pixabay.com/api/?key=](https://pixabay.com/api/?key=){api_key}"
          f"&q={quote(clean_q)}&image_type=photo&safesearch=true&per_page=5"
      )
      r = requests.get(url, timeout=12)
      r.raise_for_status()
      hits = r.json().get("hits", [])
      for hit in hits:
        img_url = hit.get("webformatURL") or hit.get("largeImageURL")
        if img_url and _download_valid_img(img_url, out_path):
          return out_path
    except Exception as e:
      print("Pixabay skip:", clean_q, e)

  return build_realistic_sticker(query, urdu_label, out_path)


def fit_photo(path: str, w: int, h: int) -> Image.Image:
  im = Image.open(path).convert("RGB")
  scale = max(w / im.width, h / im.height)
  nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
  im = im.resize((nw, nh), Image.Resampling.LANCZOS)
  x0 = max(0, (nw - w) // 2)
  y0 = max(0, (nh - h) // 2)
  return im.crop((x0, y0, x0 + w, y0 + h))


def make_smooth_background() -> Image.Image:
  base = Image.new("RGB", (W, H), (18, 138, 102))
  draw = ImageDraw.Draw(base)
  for y in range(H):
    t = y / H
    r = int(16 + 18 * t)
    g = int(152 - 54 * t)
    b = int(110 - 32 * t)
    draw.line([(0, y), (W, y)], fill=(r, g, b))

  glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
  gdraw = ImageDraw.Draw(glow)
  gdraw.ellipse([80, 130, 1000, 740], fill=(125, 255, 198, 72))
  glow = glow.filter(ImageFilter.GaussianBlur(68))
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


def render_state_frame(
    item: dict,
    thumb_paths: list[str],
    out_png: str,
    timer_num: int | None = None,
    show_answer: bool = False,
) -> str:
  bg = make_smooth_background().convert("RGBA")

  q_font = get_urdu_font(76)
  opt_font = get_urdu_font(62)
  ans_font = get_urdu_font(50)
  badge_font = get_latin_font(48)
  timer_font = get_latin_font(62)

  draw_smooth_card(
      bg,
      [54, 175, 1026, 595],
      radius=38,
      fill=(255, 255, 255, 255),
      outline=(15, 20, 28, 255),
      glow_color=(135, 255, 200, 95),
      width=6,
  )
  tdraw = ImageDraw.Draw(bg)
  tdraw.multiline_text(
      (540, 385),
      urdu_text(item["question"]),
      fill=(10, 12, 16, 255),
      font=q_font,
      anchor="mm",
      align="center",
      spacing=22,
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

  for idx, (_, _, label) in enumerate(item["options"][:3]):
    y1 = start_y + idx * (row_h + gap)
    y2 = y1 + row_h
    is_win = show_answer and (idx == correct_idx)

    fill_col = (212, 255, 226, 255) if is_win else (255, 255, 255, 255)
    out_col = (14, 155, 68, 255) if is_win else (15, 20, 28, 255)
    glow_col = (55, 245, 125, 155) if is_win else (255, 245, 180, 75)
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
        [82, y1 + 14, 132, y1 + 62],
        radius=12,
        fill=(18, 135, 62) if is_win else (20, 28, 45),
    )
    row_draw.text(
        (107, y1 + 38),
        b_letter,
        fill=(255, 255, 255),
        font=badge_font,
        anchor="mm",
    )

    row_draw.text(
        (865, y1 + row_h // 2),
        urdu_text(label),
        fill=(10, 12, 16, 255),
        font=opt_font,
        anchor="rm",
    )

  if timer_num is not None and not show_answer:
    draw_smooth_card(
        bg,
        [385, 1345, 565, 1455],
        radius=28,
        fill=(18, 24, 36, 255),
        outline=(255, 215, 70, 255),
        glow_color=(255, 215, 70, 140),
        width=5,
    )
    fdraw = ImageDraw.Draw(bg)
    fdraw.text(
        (475, 1400),
        str(timer_num),
        fill=(255, 228, 85, 255),
        font=timer_font,
        anchor="mm",
    )

  if show_answer and item.get("answer_label"):
    draw_smooth_card(
        bg,
        [54, 1345, 895, 1455],
        radius=28,
        fill=(14, 120, 56, 255),
        outline=(255, 255, 255, 255),
        glow_color=(55, 245, 125, 155),
        width=6,
    )
    fdraw = ImageDraw.Draw(bg)
    fdraw.text(
        (475, 1400),
        urdu_text(item["answer_label"]),
        fill=(255, 255, 255, 255),
        font=ans_font,
        anchor="mm",
    )

  bg.convert("RGB").save(out_png)
  return out_png


async def _tts_save(text: str, out_mp3: str, rate: str = "+0%", pitch: str = "-2Hz"):
  for voice in ["ur-PK-AsadNeural", "ur-PK-UzmaNeural"]:
    try:
      comm = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
      await comm.save(out_mp3)
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
    subprocess.run(
        [
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
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
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
  """
  No fixed cut-off:
  1. Voice speaks full question & options completely.
  2. 5-second countdown with crisp clock-second 'tick' every 1.0s.
  3. 'teeeeeennnnnnn' tone right after 5s, followed by spoken answer.
  """
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

  # 1. Full question speech
  for i, val in enumerate(q_samples):
    if i < total_n:
      samples[i] += val

  # 2. Clock second tick ('tick' every 1.0 second across 5s timer)
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
        # Crisp clock second tick (high transient snap + warm body)
        snap = 0.34 * env * math.sin(2 * math.pi * 1650 * t_rel)
        body = 0.16 * env * math.sin(2 * math.pi * 680 * t_rel)
        samples[pos] += snap + body

  # 3. 'teeeeeennnnnnn' tone + spoken answer
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
  work_dir = "quiz_build"
  os.makedirs(work_dir, exist_ok=True)
  print("Using Urdu font:", URDU_FONT_FILE)

  quiz_items = generate_gemini_quiz()
  video_parts = []
  audio_parts = []
  total_video_sec = 0.0

  for q_idx, item in enumerate(quiz_items[:2]):
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
      png_p = os.path.join(work_dir, f"q{q_idx+1}_{tag}.png")
      mp4_p = os.path.join(work_dir, f"q{q_idx+1}_{tag}.mp4")
      render_state_frame(
          item, thumb_paths, png_p, timer_num=t_num, show_answer=is_ans
      )
      subprocess.run(
          [
              "ffmpeg",
              "-y",
              "-loop",
              "1",
              "-i",
              png_p,
              "-t",
              f"{dur:.3f}",
              "-vf",
              f"scale={W}:{H},fps=30,format=yuv420p",
              "-c:v",
              "libx264",
              "-preset",
              "fast",
              "-crf",
              "22",
              mp4_p,
          ],
          check=True,
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
      )
      video_parts.append(mp4_p)

  v_list = os.path.join(work_dir, "v_list.txt")
  with open(v_list, "w", encoding="utf-8") as f:
    for vp in video_parts:
      f.write(f"file '{os.path.abspath(vp)}'\n")

  a_list = os.path.join(work_dir, "a_list.txt")
  with open(a_list, "w", encoding="utf-8") as f:
    for ap in audio_parts:
      f.write(f"file '{os.path.abspath(ap)}'\n")

  merged_v = os.path.join(work_dir, "merged_v.mp4")
  merged_a = os.path.join(work_dir, "merged_a.wav")

  subprocess.run(
      [
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
      ],
      check=True,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
  )
  subprocess.run(
      [
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
      ],
      check=True,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
  )

  final_dur = min(59.0, total_video_sec)
  subprocess.run(
      [
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
      ],
      check=True,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
  )

  save_history([x["question"] for x in quiz_items[:2]])
  print(f"Successfully built {FINAL_MP4} ({final_dur:.1f}s)")


if __name__ == "__main__":
  main()
