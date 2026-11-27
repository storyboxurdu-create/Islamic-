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
        "question": "اللہ اپنے بندے سے\nکب سب سے زیادہ\nخوش ہوتا ہے؟",
        "options": [
            ("A)", "sleep bed night stars", "جب وہ سوتا ہے"),
            ("B)", "football soccer field", "جب وہ کھیلتا ہے"),
            ("C)", "quran mosque prayer", "جب وہ توبہ کرتا ہے"),
        ],
        "correct_index": 2,
        "answer_label": "درست جواب: C — جب وہ توبہ کرتا ہے",
        "question_speech": (
            "اللہ اپنے بندے سے کب سب سے زیادہ خوش ہوتا ہے؟ "
            "سوتا ہے، کھیلتا ہے، یا توبہ کرتا ہے؟"
        ),
        "answer_speech": "درست جواب ہے: جب وہ توبہ کرتا ہے۔",
    },
    {
        "question": "اسلام کی سب سے پہلی\nمسجد کون سی ہے؟",
        "options": [
            ("A)", "white quba mosque dome", "مسجدِ قبا"),
            ("B)", "green dome prophet mosque", "مسجدِ نبوی"),
            ("C)", "jerusalem mosque dome", "مسجدِ اقصیٰ"),
        ],
        "correct_index": 0,
        "answer_label": "درست جواب: A — مسجدِ قبا",
        "question_speech": (
            "اسلام کی سب سے پہلی مسجد کون سی ہے؟ "
            "مسجدِ قبا، مسجدِ نبوی، یا مسجدِ اقصیٰ؟"
        ),
        "answer_speech": "درست جواب ہے: مسجدِ قبا۔",
    },
]


def discover_urdu_font_path() -> str | None:
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

  for p in [
      "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
      "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
      "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
  ]:
    if os.path.exists(p):
      return p
  return None


URDU_FONT_FILE = discover_urdu_font_path()


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
    Fixes Urdu character joining AND right-to-left display order in PIL.
    """
  if not text:
    return ""
  lines = []
  for raw in text.split("\n"):
    s = raw.strip()
    if not s:
      lines.append("")
      continue
    if HAS_BIDI:
      reshaped = arabic_reshaper.reshape(s)
      bidi_str = get_display(reshaped)
      # In PIL, reversing shaped display string fixes reversed characters like 'دجسم' -> 'مسجد'
      lines.append(bidi_str[::-1])
    else:
      lines.append(s[::-1])
  return "\n".join(lines)


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
Generate 2 short, clear Islamic quiz questions in Urdu for a 30-second YouTube Short (15 seconds per question).
Rules:
- Each question: max 2 short lines, 3-5 Urdu words per line.
- Each option (A, B, C): short Urdu phrase (2-3 words) + clear English photo keyword phrase.
- Include correct_index (0, 1, or 2), answer_label in Urdu, question_speech in natural Urdu (~4.5s), and answer_speech in natural Urdu (~2s).
- Avoid repeating these questions:
{avoid_text}

Return ONLY valid JSON list of 2 items:
[
  {{
    "question": "مختصر اردو سوال سطر 1\\nسطر 2",
    "options": [
      ["A)", "photo topic 1", "اردو آپشن 1"],
      ["B)", "photo topic 2", "اردو آپشن 2"],
      ["C)", "photo topic 3", "اردو آپشن 3"]
    ],
    "correct_index": 1,
    "answer_label": "درست جواب: B — اردو آپشن 2",
    "question_speech": "مختصر اردو سوال؟",
    "answer_speech": "درست جواب ہے: اردو آپشن 2۔"
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


def build_illustrated_scene_thumb(
    prompt: str, out_path: str, w: int = 320, h: int = 240
) -> str:
  """
    Creates a detailed pictorial scene matching the topic if external photo APIs are unreachable.
    """
  low = (prompt or "").lower()
  img = Image.new("RGB", (w, h), (135, 195, 235))
  draw = ImageDraw.Draw(img)

  if any(k in low for k in ["mosque", "masjid", "quba", "dome", "jerusalem"]):
    # Sky + sun + mosque dome & minaret silhouette/scene
    for y in range(int(h * 0.72)):
      t = y / max(1, h * 0.72)
      draw.line(
          [(0, y), (w, y)],
          fill=(
              int(90 + 110 * t),
              int(165 + 55 * t),
              int(230 - 30 * t),
          ),
      )
    draw.ellipse([w - 90, 22, w - 34, 78], fill=(255, 225, 110))
    draw.rectangle([0, int(h * 0.72), w, h], fill=(75, 145, 85))
    # Mosque base + dome + crescent
    draw.rectangle(
        [int(w * 0.22), int(h * 0.46), int(w * 0.78), int(h * 0.74)],
        fill=(245, 242, 232),
        outline=(170, 160, 140),
        width=2,
    )
    draw.pieslice(
        [int(w * 0.30), int(h * 0.24), int(w * 0.70), int(h * 0.64)],
        180,
        360,
        fill=(42, 138, 88) if "green" in low else (240, 238, 228),
        outline=(30, 80, 50),
        width=2,
    )
    # Minaret
    draw.rectangle(
        [int(w * 0.14), int(h * 0.28), int(w * 0.22), int(h * 0.74)],
        fill=(245, 242, 232),
        outline=(170, 160, 140),
        width=2,
    )
    draw.polygon(
        [
            (int(w * 0.13), int(h * 0.28)),
            (int(w * 0.18), int(h * 0.16)),
            (int(w * 0.23), int(h * 0.28)),
        ],
        fill=(42, 138, 88),
    )
  elif any(k in low for k in ["quran", "book", "prayer", "pray"]):
    # Warm study/prayer scene with open book/pages
    for y in range(h):
      draw.line([(0, y), (w, y)], fill=(55 + y // 5, 42 + y // 6, 30))
    draw.ellipse([w // 2 - 70, 24, w // 2 + 70, 164], fill=(255, 215, 110))
    draw.polygon(
        [
            (45, int(h * 0.45)),
            (w // 2, int(h * 0.52)),
            (w // 2, int(h * 0.84)),
            (45, int(h * 0.78)),
        ],
        fill=(252, 248, 235),
        outline=(160, 130, 75),
    )
    draw.polygon(
        [
            (w - 45, int(h * 0.45)),
            (w // 2, int(h * 0.52)),
            (w // 2, int(h * 0.84)),
            (w - 45, int(h * 0.78)),
        ],
        fill=(252, 248, 235),
        outline=(160, 130, 75),
    )
    for line_i in range(4):
      yy = int(h * 0.54) + line_i * 18
      draw.line([(75, yy), (w // 2 - 20, yy + 6)], fill=(120, 100, 70), width=2)
      draw.line(
          [(w // 2 + 20, yy + 6), (w - 75, yy)], fill=(120, 100, 70), width=2
      )
  elif any(k in low for k in ["sleep", "bed", "night", "stars"]):
    # Night sky + moon + stars + bed
    for y in range(h):
      draw.line([(0, y), (w, y)], fill=(18 + y // 8, 28 + y // 7, 68 + y // 6))
    draw.ellipse([w - 95, 24, w - 35, 84], fill=(250, 238, 175))
    for sx, sy in [(45, 40), (95, 75), (145, 35), (190, 68)]:
      draw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=(255, 255, 210))
    draw.rectangle(
        [35, int(h * 0.65), w - 35, int(h * 0.85)], fill=(120, 75, 45)
    )
    draw.rectangle(
        [45, int(h * 0.55), 115, int(h * 0.66)], fill=(240, 240, 248)
    )
    draw.rectangle(
        [115, int(h * 0.58), w - 45, int(h * 0.66)], fill=(70, 120, 190)
    )
  else:
    # Field + ball / outdoor daytime scene
    for y in range(int(h * 0.62)):
      draw.line([(0, y), (w, y)], fill=(115, 190, 245))
    draw.rectangle([0, int(h * 0.62), w, h], fill=(52, 155, 72))
    draw.ellipse([35, 24, 95, 84], fill=(255, 220, 80))
    cx, cy, r = w // 2, int(h * 0.68), 38
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=(250, 250, 250),
        outline=(30, 30, 30),
        width=3,
    )
    draw.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=(35, 35, 35))

  img.save(out_path)
  return out_path


def fetch_real_photo(prompt: str, out_path: str) -> str:
  api_key = os.environ.get("PIXABAY_API_KEY", "").strip()
  if api_key and prompt:
    try:
      q = quote(" ".join(prompt.split()[:4]))
      url = f"[https://pixabay.com/api/?key=](https://pixabay.com/api/?key=){api_key}&q={q}&image_type=photo&safesearch=true&per_page=3"
      r = requests.get(url, timeout=15)
      r.raise_for_status()
      hits = r.json().get("hits", [])
      if hits:
        img_url = hits[0].get("webformatURL") or hits[0].get("largeImageURL")
        if img_url:
          ir = requests.get(img_url, timeout=20)
          ir.raise_for_status()
          with open(out_path, "wb") as f:
            f.write(ir.content)
          Image.open(out_path).verify()
          return out_path
    except Exception as e:
      print("Pixabay fetch skipped:", e)

  try:
    photo_prompt = quote(
        f"realistic photography, {prompt}, clear subject, natural light, no text"
    )
    seed = random.randint(1000, 999999)
    p_url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){photo_prompt}?width=360&height=260&seed={seed}&nologo=true"
    pr = requests.get(p_url, timeout=20)
    pr.raise_for_status()
    with open(out_path, "wb") as f:
      f.write(pr.content)
    Image.open(out_path).verify()
    return out_path
  except Exception as e:
    print("Pollinations fallback:", e)

  return build_illustrated_scene_thumb(prompt, out_path)


def fit_photo(path: str, w: int, h: int) -> Image.Image:
  im = Image.open(path).convert("RGB")
  scale = max(w / im.width, h / im.height)
  nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
  im = im.resize((nw, nh), Image.Resampling.LANCZOS)
  x0 = max(0, (nw - w) // 2)
  y0 = max(0, (nh - h) // 2)
  return im.crop((x0, y0, x0 + w, y0 + h))


def make_smooth_background() -> Image.Image:
  base = Image.new("RGB", (W, H), (232, 182, 92))
  draw = ImageDraw.Draw(base)
  for y in range(H):
    t = y / H
    r = int(240 - 28 * t)
    g = int(194 - 44 * t)
    b = int(106 - 32 * t)
    draw.line([(0, y), (W, y)], fill=(r, g, b))
  glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
  gdraw = ImageDraw.Draw(glow)
  gdraw.ellipse([120, 180, 960, 820], fill=(255, 232, 175, 75))
  glow = glow.filter(ImageFilter.GaussianBlur(60))
  return Image.alpha_composite(base.convert("RGBA"), glow).convert("RGB")


def draw_shadow_round_box(
    canvas_rgba: Image.Image,
    box: list[int],
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    width: int = 5,
):
  shadow = Image.new("RGBA", canvas_rgba.size, (0, 0, 0, 0))
  sdraw = ImageDraw.Draw(shadow)
  sx1, sy1, sx2, sy2 = box[0] + 6, box[1] + 10, box[2] + 6, box[3] + 10
  sdraw.rounded_rectangle(
      [sx1, sy1, sx2, sy2], radius=radius, fill=(0, 0, 0, 55)
  )
  shadow = shadow.filter(ImageFilter.GaussianBlur(10))
  canvas_rgba.alpha_composite(shadow)

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

  q_font = get_urdu_font(64)
  opt_font = get_urdu_font(52)
  ans_font = get_urdu_font(44)
  badge_font = get_latin_font(52)
  timer_font = get_latin_font(68)

  draw_shadow_round_box(
      bg,
      [56, 220, 1024, 690],
      radius=42,
      fill=(255, 255, 255, 252),
      outline=(35, 35, 35, 230),
      width=5,
  )
  tdraw = ImageDraw.Draw(bg)
  tdraw.multiline_text(
      (540, 455),
      urdu_text(item["question"]),
      fill=(15, 15, 15, 255),
      font=q_font,
      anchor="mm",
      align="center",
      spacing=20,
  )

  start_y = 740
  row_h = 225
  gap = 28
  correct_idx = item.get("correct_index", 0)

  for idx, (_, _, label) in enumerate(item["options"][:3]):
    y1 = start_y + idx * (row_h + gap)
    y2 = y1 + row_h
    is_win = show_answer and (idx == correct_idx)

    fill_col = (224, 252, 232, 255) if is_win else (255, 255, 255, 252)
    out_col = (16, 145, 68, 255) if is_win else (40, 75, 185, 235)
    b_w = 8 if is_win else 5

    draw_shadow_round_box(
        bg,
        [56, y1, 895, y2],
        radius=32,
        fill=fill_col,
        outline=out_col,
        width=b_w,
    )

    row_draw = ImageDraw.Draw(bg)
    badge_letter = f"{['A', 'B', 'C'][idx]})"
    b_fill = (20, 130, 62) if is_win else (245, 247, 252)
    b_fg = (255, 255, 255) if is_win else (15, 15, 15)

    row_draw.rounded_rectangle(
        [74, y1 + 22, 192, y2 - 22],
        radius=20,
        fill=b_fill,
        outline=(25, 25, 25),
        width=4,
    )
    row_draw.text(
        (133, y1 + row_h // 2),
        badge_letter,
        fill=b_fg,
        font=badge_font,
        anchor="mm",
    )

    photo = fit_photo(thumb_paths[idx], 225, row_h - 36)
    bg.paste(photo, (208, y1 + 18))

    row_draw.text(
        (868, y1 + row_h // 2),
        urdu_text(label),
        fill=(12, 12, 12, 255),
        font=opt_font,
        anchor="rm",
    )

  if timer_num is not None and not show_answer:
    draw_shadow_round_box(
        bg,
        [390, 1525, 560, 1655],
        radius=34,
        fill=(25, 25, 25, 245),
        outline=(255, 215, 70, 255),
        width=5,
    )
    fdraw = ImageDraw.Draw(bg)
    fdraw.text(
        (475, 1590),
        str(timer_num),
        fill=(255, 225, 75, 255),
        font=timer_font,
        anchor="mm",
    )

  if show_answer and item.get("answer_label"):
    draw_shadow_round_box(
        bg,
        [56, 1525, 895, 1655],
        radius=30,
        fill=(14, 108, 52, 255),
        outline=(255, 255, 255, 255),
        width=5,
    )
    fdraw = ImageDraw.Draw(bg)
    fdraw.text(
        (475, 1590),
        urdu_text(item["answer_label"]),
        fill=(255, 255, 255, 255),
        font=ans_font,
        anchor="mm",
    )

  bg.convert("RGB").save(out_png)
  return out_png


async def _tts_speak(text: str, out_mp3: str, rate: str = "+5%"):
  for voice in ["ur-PK-UzmaNeural", "ur-PK-AsadNeural"]:
    try:
      comm = edge_tts.Communicate(text, voice=voice, rate=rate, pitch="+0Hz")
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
  if not (HAS_TTS and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 400):
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
          samples[pos] += (raw[i] / 32768.0) * 0.95
  except Exception as e:
    print("Mix speech error:", tag, e)


def build_question_audio_15s(item: dict, out_wav: str, work_dir: str) -> str:
  """
  15s per question:
  - 0.0s  .. 5.5s  : Question & options spoken by voice
  - 5.5s  .. 10.5s : Fast tick-tick-tick timer during 5-second countdown
  - 10.5s .. 11.3s : Final 'too' (teeeeeennnnnnn) tone
  - 11.4s .. 15.0s : Spoken answer ("درست جواب ہے...")
  """
  sr = 44100
  total_samples = int(PER_QUESTION_SEC * sr)
  samples = [0.0] * total_samples

  q_speech = item.get("question_speech", "")
  a_speech = item.get("answer_speech", item.get("answer_label", ""))
  base_name = os.path.basename(out_wav)

  if HAS_TTS and q_speech.strip():
    q_mp3 = os.path.join(work_dir, f"{base_name}_q.mp3")
    asyncio.run(_tts_speak(q_speech, q_mp3, rate="+8%"))
    _mix_mp3_into_samples(q_mp3, samples, 0.0, 5.4, sr, work_dir, f"{base_name}_q")

  # Fast 'tik-tik-tik' every 0.25s across the 5-second timer window (5.5s .. 10.5s)
  tick_t = 5.5
  while tick_t < 10.5:
    start_i = int(tick_t * sr)
    tick_len = int(0.055 * sr)
    for k in range(tick_len):
      idx = start_i + k
      if idx < total_samples:
        env = math.exp(-k / (0.015 * sr))
        samples[idx] += 0.45 * env * math.sin(2 * math.pi * 1320 * (k / sr))
    tick_t += 0.25

  # Final 'too' (teeeeeennnnnnn) at 10.5s .. 11.3s
  b_start = int(10.5 * sr)
  b_len = int(0.8 * sr)
  for k in range(b_len):
    idx = b_start + k
    if idx < total_samples:
      t_rel = k / sr
      fade_in = min(1.0, k / (0.015 * sr))
      fade_out = min(1.0, (b_len - k) / (0.06 * sr))
      tone = 0.34 * math.sin(2 * math.pi * 680 * t_rel) + 0.14 * math.sin(
          2 * math.pi * 1360 * t_rel
      )
      samples[idx] += tone * fade_in * fade_out

  # Spoken answer right after 'too' (11.4s .. 15.0s)
  if HAS_TTS and a_speech.strip():
    a_mp3 = os.path.join(work_dir, f"{base_name}_a.mp3")
    asyncio.run(_tts_speak(a_speech, a_mp3, rate="+5%"))
    _mix_mp3_into_samples(a_mp3, samples, 11.4, 3.5, sr, work_dir, f"{base_name}_a")

  with wave.open(out_wav, "wb") as out_wf:
    out_wf.setnchannels(2)
    out_wf.setsampwidth(2)
    out_wf.setframerate(sr)
    packed = bytearray()
    for s in samples:
      clamped = max(-0.98, min(0.98, s))
      iv = int(clamped * 32767)
      packed.extend(struct.pack("<hh", iv, iv))
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
    for o_idx, (_, photo_query, _) in enumerate(item["options"][:3]):
      p_file = os.path.join(work_dir, f"q{q_idx+1}_opt{o_idx+1}.jpg")
      thumb_paths.append(fetch_real_photo(photo_query, p_file))

    # 15.0s per question:
    # 0.0..5.5s   (5.5s) : Question & options while voice speaks
    # 5.5..10.5s  (5.0s) : 5-second countdown (5..1) with fast tick-tick
    # 10.5..15.0s (4.5s) : Final 'too' + answer highlight + spoken answer
    slots = [
        ("q_intro", 5.5, None, False),
        ("t_5", 1.0, 5, False),
        ("t_4", 1.0, 4, False),
        ("t_3", 1.0, 3, False),
        ("t_2", 1.0, 2, False),
        ("t_1", 1.0, 1, False),
        ("t_ans", 4.5, None, True),
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
