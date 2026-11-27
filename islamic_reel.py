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
PER_QUESTION_SEC = 15.0
TOTAL_SEC = 30.0
FINAL_MP4 = "final_islamic_short.mp4"
HISTORY_FILE = "islamic_history.json"

FALLBACK_QUIZ = [
    {
        "question": "زندگی کی آخری ساعتوں میں\nانسان کو کیا یاد آتا ہے؟",
        "options": [
            ("A)", "money cash coins bag", "دولت"),
            ("B)", "family parents love care", "رشتے"),
            ("C)", "regret mistake cross", "غلطیاں"),
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
            ("A)", "sleeping night bed", "جب وہ سوتا ہے"),
            ("B)", "football sport field", "جب وہ کھیلتا ہے"),
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
    Shapes Urdu text and applies RTL display order ONCE without double-reversing words.
    """
  if not text:
    return ""
  out_lines = []
  for raw_line in text.split("\n"):
    line = raw_line.strip()
    if not line:
      out_lines.append("")
      continue
    if HAS_RESHAPER:
      shaped = arabic_reshaper.reshape(line)
      if HAS_BIDI:
        out_lines.append(get_display(shaped))
      else:
        out_lines.append(shaped)
    else:
      out_lines.append(line)
  return "\n".join(out_lines)


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
Generate 2 short, emotional, easy-to-understand Islamic quiz questions in Urdu for a 30-second YouTube Short (15 seconds per question).
Rules:
- Use clear, everyday Urdu words (max 2 short lines per question, 1-4 Urdu words per option).
- Each option (A, B, C) must include a clear 2-3 word English keyword for photo search.
- Include correct_index (0, 1, or 2), answer_label in simple Urdu, question_speech (warm natural Urdu spoken in ~5-6 seconds), and answer_speech (warm natural Urdu spoken in ~2 seconds).
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
  if len(r.content) < 1200:
    return False
  with open(out_path, "wb") as f:
    f.write(r.content)
  with Image.open(out_path) as im:
    im.verify()
  return True


def build_rich_photo_card(
    query: str, urdu_label: str, out_path: str, w: int = 320, h: int = 200
) -> str:
  """
    Creates a clean, high-contrast visual card with topic styling + Urdu/badge when external APIs are blocked.
    """
  low = f"{query} {urdu_label}".lower()
  img = Image.new("RGB", (w, h), (245, 248, 252))
  draw = ImageDraw.Draw(img)

  if any(k in low for k in ["money", "cash", "coin", "دولت", "پیسہ", "مال"]):
    # Warm gold & currency card
    for y in range(h):
      t = y / h
      draw.line([(0, y), (w, y)], fill=(int(248 - 25 * t), int(215 - 45 * t), int(110 - 30 * t)))
    draw.rounded_rectangle([55, 45, w - 55, h - 45], radius=24, fill=(42, 130, 72), outline=(255, 255, 255), width=3)
    draw.ellipse([w // 2 - 42, h // 2 - 42, w // 2 + 42, h // 2 + 42], fill=(255, 215, 65))
  elif any(k in low for k in ["family", "parent", "love", "رشتے", "ماں", "باپ", "بچے"]):
    # Soft warm rose-amber card with connected hearts/circles
    for y in range(h):
      t = y / h
      draw.line([(0, y), (w, y)], fill=(int(252 - 20 * t), int(218 - 40 * t), int(212 - 35 * t)))
    draw.ellipse([w // 2 - 75, h // 2 - 36, w // 2 - 5, h // 2 + 34], fill=(225, 75, 95))
    draw.ellipse([w // 2 + 5, h // 2 - 36, w // 2 + 75, h // 2 + 34], fill=(235, 110, 65))
  elif any(k in low for k in ["mistake", "regret", "cross", "غلطیاں", "گناہ", "غلط"]):
    # Soft coral-slate card with bold X mark
    for y in range(h):
      t = y / h
      draw.line([(0, y), (w, y)], fill=(int(252 - 15 * t), int(210 - 35 * t), int(210 - 35 * t)))
    cx, cy = w // 2, h // 2
    draw.ellipse([cx - 52, cy - 52, cx + 52, cy + 52], fill=(215, 45, 55))
    draw.line([(cx - 24, cy - 24), (cx + 24, cy + 24)], fill=(255, 255, 255), width=8)
    draw.line([(cx + 24, cy - 24), (cx - 24, cy + 24)], fill=(255, 255, 255), width=8)
  elif any(k in low for k in ["mosque", "masjid", "quran", "prayer", "توبہ", "مسجد", "نماز", "قرآن"]):
    # Emerald & gold sacred motif
    for y in range(h):
      t = y / h
      draw.line([(0, y), (w, y)], fill=(int(26 + 20 * t), int(138 - 25 * t), int(102 - 20 * t)))
    draw.pieslice([w // 2 - 65, 35, w // 2 + 65, 165], 180, 360, fill=(255, 222, 115))
    draw.rectangle([w // 2 - 65, 98, w // 2 + 65, h - 32], fill=(255, 250, 235))
  else:
    # Clean blue-teal card
    for y in range(h):
      t = y / h
      draw.line([(0, y), (w, y)], fill=(int(70 + 40 * t), int(145 + 35 * t), int(215 - 20 * t)))
    draw.ellipse([w // 2 - 48, h // 2 - 48, w // 2 + 48, h // 2 + 48], fill=(255, 255, 255))

  img.save(out_path)
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

  if clean_q:
    try:
      p_prompt = quote(f"realistic photo of {clean_q}, clean lighting, no text")
      seed = random.randint(1000, 999999)
      p_url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){p_prompt}?width=420&height=300&seed={seed}&nologo=true"
      if _download_valid_img(p_url, out_path, timeout=15):
        return out_path
    except Exception as e:
      print("Pollinations skip:", clean_q, e)

  return build_rich_photo_card(query, urdu_label, out_path)


def fit_photo(path: str, w: int, h: int) -> Image.Image:
  im = Image.open(path).convert("RGB")
  scale = max(w / im.width, h / im.height)
  nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
  im = im.resize((nw, nh), Image.Resampling.LANCZOS)
  x0 = max(0, (nw - w) // 2)
  y0 = max(0, (nh - h) // 2)
  return im.crop((x0, y0, x0 + w, y0 + h))


def make_smooth_background() -> Image.Image:
  base = Image.new("RGB", (W, H), (22, 148, 108))
  draw = ImageDraw.Draw(base)
  for y in range(H):
    t = y / H
    r = int(20 + 16 * t)
    g = int(160 - 52 * t)
    b = int(116 - 30 * t)
    draw.line([(0, y), (W, y)], fill=(r, g, b))

  glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
  gdraw = ImageDraw.Draw(glow)
  gdraw.ellipse([90, 140, 990, 740], fill=(130, 255, 200, 70))
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
  timer_font = get_latin_font(64)

  # Top white question card
  draw_smooth_card(
      bg,
      [54, 185, 1026, 615],
      radius=38,
      fill=(255, 255, 255, 255),
      outline=(15, 20, 28, 255),
      glow_color=(140, 255, 200, 95),
      width=6,
  )
  tdraw = ImageDraw.Draw(bg)
  q_str = urdu_text(item["question"])
  tdraw.multiline_text(
      (540, 400),
      q_str,
      fill=(10, 12, 16, 255),
      font=q_font,
      anchor="mm",
      align="center",
      spacing=22,
  )

  # Progress bar during 5-second timer
  if timer_num is not None and not show_answer:
    bx1, by1, bx2, by2 = 85, 642, 865, 686
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

  # 3 Option cards (A, B, C)
  start_y = 710
  row_h = 205
  gap = 24
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
    photo = fit_photo(thumb_paths[idx], 235, row_h - 28)
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

    opt_str = urdu_text(label)
    row_draw.text(
        (865, y1 + row_h // 2),
        opt_str,
        fill=(10, 12, 16, 255),
        font=opt_font,
        anchor="rm",
    )

  # Countdown badge
  if timer_num is not None and not show_answer:
    draw_smooth_card(
        bg,
        [385, 1385, 565, 1500],
        radius=30,
        fill=(18, 24, 36, 255),
        outline=(255, 215, 70, 255),
        glow_color=(255, 215, 70, 140),
        width=5,
    )
    fdraw = ImageDraw.Draw(bg)
    fdraw.text(
        (475, 1442),
        str(timer_num),
        fill=(255, 228, 85, 255),
        font=timer_font,
        anchor="mm",
    )

  # Answer banner cleanly above Shorts footer icons
  if show_answer and item.get("answer_label"):
    draw_smooth_card(
        bg,
        [54, 1385, 895, 1500],
        radius=28,
        fill=(14, 120, 56, 255),
        outline=(255, 255, 255, 255),
        glow_color=(55, 245, 125, 155),
        width=6,
    )
    fdraw = ImageDraw.Draw(bg)
    ans_str = urdu_text(item["answer_label"])
    fdraw.text(
        (475, 1442),
        ans_str,
        fill=(255, 255, 255, 255),
        font=ans_font,
        anchor="mm",
    )

  bg.convert("RGB").save(out_png)
  return out_png


async def _tts_speak(text: str, out_mp3: str, rate: str = "-3%", pitch: str = "-2Hz"):
  for voice in ["ur-PK-AsadNeural", "ur-PK-UzmaNeural"]:
    try:
      comm = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
      await comm.save(out_mp3)
      if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 400:
        return
    except Exception as e:
      print("TTS retry:", voice, e)


def _mix_mp3_into_samples(
    mp3_path: str,
    samples: list[float],
    start_sec: float,
    max_dur_sec: float,
    sr: int,
    work_dir: str,
    tag: str,
):
  if not (
      HAS_TTS and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 400
  ):
    return
  wav_tmp = os.path.join(work_dir, f"{tag}_tmp.wav")
  try:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            mp3_path,
            "-t",
            str(max_dur_sec),
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
      s_idx = int(start_sec * sr)
      for i in range(n):
        pos = s_idx + i
        if 0 <= pos < len(samples):
          samples[pos] += (raw[i] / 32768.0) * 0.96
  except Exception as e:
    print("Mix speech error:", tag, e)


def build_question_audio_15s(item: dict, out_wav: str, work_dir: str) -> str:
  """
  15s per question:
  - 0.0s  .. 6.1s  : Expressive Urdu voice speaks question & options
  - 6.2s  .. 11.2s : Gentle soft bell/chime pulse across 5s timer
  - 11.2s .. 12.0s : 'teeeeeennnnnnn' tone
  - 12.1s .. 15.0s : Voice speaks answer clearly
  """
  sr = 44100
  total_samples = int(PER_QUESTION_SEC * sr)
  samples = [0.0] * total_samples

  q_speech = item.get("question_speech", "")
  a_speech = item.get("answer_speech", item.get("answer_label", ""))
  base_name = os.path.basename(out_wav)

  if HAS_TTS and q_speech.strip():
    q_mp3 = os.path.join(work_dir, f"{base_name}_q.mp3")
    asyncio.run(_tts_speak(q_speech, q_mp3, rate="+0%", pitch="-2Hz"))
    _mix_mp3_into_samples(
        q_mp3, samples, 0.0, 6.1, sr, work_dir, f"{base_name}_q"
    )

  # Gentle soft bell pulse every 1.0s (5 soft pulses across 5s timer)
  for idx_sec in range(5):
    t_start = 6.2 + idx_sec * 1.0
    start_i = int(t_start * sr)
    dur_len = int(0.22 * sr)
    for k in range(dur_len):
      idx = start_i + k
      if idx < total_samples:
        t_rel = k / sr
        env = math.exp(-k / (0.06 * sr))
        val = 0.16 * env * math.sin(2 * math.pi * 587.33 * t_rel)
        samples[idx] += val

  # 'teeeeeennnnnnn' tone (11.2s .. 12.0s)
  b_start = int(11.2 * sr)
  b_len = int(0.8 * sr)
  for k in range(b_len):
    idx = b_start + k
    if idx < total_samples:
      t_rel = k / sr
      fade_in = min(1.0, k / (0.015 * sr))
      fade_out = min(1.0, (b_len - k) / (0.06 * sr))
      tone = 0.28 * math.sin(2 * math.pi * 660 * t_rel) + 0.11 * math.sin(
          2 * math.pi * 1320 * t_rel
      )
      samples[idx] += tone * fade_in * fade_out

  # Spoken answer after 'teeeeeennnnnnn' (12.1s .. 15.0s)
  if HAS_TTS and a_speech.strip():
    a_mp3 = os.path.join(work_dir, f"{base_name}_a.mp3")
    asyncio.run(_tts_speak(a_speech, a_mp3, rate="-2%", pitch="-2Hz"))
    _mix_mp3_into_samples(
        a_mp3, samples, 12.1, 2.8, sr, work_dir, f"{base_name}_a"
    )

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

  return out_wav


def main():
  work_dir = "quiz_build"
  os.makedirs(work_dir, exist_ok=True)
  print("Using Urdu font:", URDU_FONT_FILE)

  quiz_items = generate_gemini_quiz()
  video_parts = []
  audio_parts = []

  for q_idx, item in enumerate(quiz_items[:2]):
    thumb_paths = []
    for o_idx, (_, photo_query, urdu_label) in enumerate(item["options"][:3]):
      p_file = os.path.join(work_dir, f"q{q_idx+1}_opt{o_idx+1}.jpg")
      thumb_paths.append(fetch_option_photo(photo_query, urdu_label, p_file))

    slots = [
        ("q_intro", 6.2, None, False),
        ("t_5", 1.0, 5, False),
        ("t_4", 1.0, 4, False),
        ("t_3", 1.0, 3, False),
        ("t_2", 1.0, 2, False),
        ("t_1", 1.0, 1, False),
        ("t_ans", 3.8, None, True),
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
              str(dur),
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

    wav_p = os.path.join(work_dir, f"q{q_idx+1}_15s.wav")
    build_question_audio_15s(item, wav_p, work_dir)
    audio_parts.append(wav_p)

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

  subprocess.run(
      [
          "ffmpeg",
          "-y",
          "-i",
          merged_v,
          "-i",
          merged_a,
          "-t",
          str(int(TOTAL_SEC)),
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
  print("Successfully built:", FINAL_MP4)


if __name__ == "__main__":
  main()
