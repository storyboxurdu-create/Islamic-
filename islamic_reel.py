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
            ("A)", "person sleeping peaceful bedroom night", "جب وہ سوتا ہے"),
            ("B)", "football match green stadium grass", "جب وہ کھیلتا ہے"),
            ("C)", "open quran book mosque light", "جب وہ توبہ کرتا ہے"),
        ],
        "correct_index": 2,
        "answer_label": "درست جواب: جب وہ توبہ کرتا ہے",
        "question_speech": (
            "اللہ اپنے بندے سے کب سب سے زیادہ خوش ہوتا ہے؟ "
            "سوتا ہے، کھیلتا ہے، یا توبہ کرتا ہے؟"
        ),
        "answer_speech": "درست جواب ہے: جب وہ توبہ کرتا ہے۔",
    },
    {
        "question": "اسلام کی سب سے پہلی\nمسجد کون سی ہے؟",
        "options": [
            ("A)", "quba mosque white architecture", "مسجدِ قبا"),
            ("B)", "prophet mosque green dome medina", "مسجدِ نبوی"),
            ("C)", "al aqsa mosque dome jerusalem", "مسجدِ اقصیٰ"),
        ],
        "correct_index": 0,
        "answer_label": "درست جواب: مسجدِ قبا",
        "question_speech": (
            "اسلام کی سب سے پہلی مسجد کون سی ہے؟ "
            "مسجدِ قبا، مسجدِ نبوی، یا مسجدِ اقصیٰ؟"
        ),
        "answer_speech": "درست جواب ہے: مسجدِ قبا۔",
    },
]


def discover_bold_urdu_font() -> str | None:
  candidates = [
      "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
      "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
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


URDU_FONT_FILE = discover_bold_urdu_font()


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
Generate 2 short, clear, easy-to-understand Islamic quiz questions in Urdu for a 30-second YouTube Short (15 seconds per question).
Rules:
- Keep Urdu words simple, natural, and easy to read (max 2 short lines per question, 2-4 simple Urdu words per option).
- Each option (A, B, C) must include a clear English real-photo search description (3-4 words).
- Include correct_index (0, 1, or 2), answer_label in simple Urdu, question_speech (~4.5s), and answer_speech (~2s).
- Avoid repeating these questions:
{avoid_text}

Return ONLY valid JSON list of 2 items:
[
  {{
    "question": "آسان اردو سوال سطر 1\\nسطر 2",
    "options": [
      ["A)", "real photo query 1", "آسان آپشن 1"],
      ["B)", "real photo query 2", "آسان آپشن 2"],
      ["C)", "real photo query 3", "آسان آپشن 3"]
    ],
    "correct_index": 1,
    "answer_label": "درست جواب: آسان آپشن 2",
    "question_speech": "آسان اردو سوال؟",
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


def _try_download_image(url: str, out_path: str, timeout: int = 18) -> bool:
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


def fetch_real_photo(prompt: str, out_path: str) -> str:
  api_key = os.environ.get("PIXABAY_API_KEY", "").strip()
  if api_key and prompt:
    try:
      q = quote(" ".join(prompt.split()[:4]))
      url = f"[https://pixabay.com/api/?key=](https://pixabay.com/api/?key=){api_key}&q={q}&image_type=photo&safesearch=true&per_page=3"
      r = requests.get(url, timeout=15)
      r.raise_for_status()
      hits = r.json().get("hits", [])
      for hit in hits:
        img_url = hit.get("webformatURL") or hit.get("largeImageURL")
        if img_url and _try_download_image(img_url, out_path):
          return out_path
    except Exception as e:
      print("Pixabay fetch skipped:", e)

  # Try Pollinations real photo endpoint
  if prompt:
    try:
      photo_prompt = quote(
          f"real photograph of {prompt}, DSLR photo, natural lighting, detailed, no text"
      )
      seed = random.randint(1000, 999999)
      p_url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){photo_prompt}?width=480&height=360&seed={seed}&nologo=true"
      if _try_download_image(p_url, out_path, timeout=25):
        return out_path
    except Exception as e:
      print("Pollinations fetch skipped:", e)

  # Try Wikimedia Commons search for real photos matching keywords
  if prompt:
    try:
      q_wiki = quote(" ".join(prompt.split()[:3]))
      w_url = (
          "[https://commons.wikimedia.org/w/api.php?action=query&generator=search](https://commons.wikimedia.org/w/api.php?action=query&generator=search)"
          f"&gsrnamespace=6&gsrsearch={q_wiki}&gsrlimit=3&prop=imageinfo&iiprop=url&format=json"
      )
      wr = requests.get(w_url, headers={"User-Agent": "IslamicQuizBot/1.0"}, timeout=15)
      wr.raise_for_status()
      pages = wr.json().get("query", {}).get("pages", {})
      for page in pages.values():
        infos = page.get("imageinfo", [])
        if infos:
          u = infos[0].get("url", "")
          if u.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            if _try_download_image(u, out_path, timeout=20):
              return out_path
    except Exception as e:
      print("Wikimedia fetch skipped:", e)

  # Rich glowing fallback card if offline/blocked
  w, h = 360, 260
  im = Image.new("RGB", (w, h), (35, 55, 85))
  dr = ImageDraw.Draw(im)
  for y in range(h):
    t = y / h
    dr.line([(0, y), (w, y)], fill=(int(38 + 45 * t), int(62 + 55 * t), int(95 + 40 * t)))
  glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
  gd = ImageDraw.Draw(glow)
  gd.ellipse([60, 30, w - 60, h - 30], fill=(255, 200, 80, 95))
  glow = glow.filter(ImageFilter.GaussianBlur(28))
  im = Image.alpha_composite(im.convert("RGBA"), glow).convert("RGB")
  im.save(out_path)
  return out_path


def fit_photo(path: str, w: int, h: int) -> Image.Image:
  im = Image.open(path).convert("RGB")
  scale = max(w / im.width, h / im.height)
  nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
  im = im.resize((nw, nh), Image.Resampling.LANCZOS)
  x0 = max(0, (nw - w) // 2)
  y0 = max(0, (nh - h) // 2)
  return im.crop((x0, y0, x0 + w, y0 + h))


def make_glowing_background() -> Image.Image:
  """Vibrant warm golden-amber gradient with soft glowing aura."""
  base = Image.new("RGB", (W, H), (228, 162, 52))
  draw = ImageDraw.Draw(base)
  for y in range(H):
    t = y / H
    r = int(246 - 48 * t)
    g = int(186 - 62 * t)
    b = int(72 - 28 * t)
    draw.line([(0, y), (W, y)], fill=(r, g, b))

  glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
  gdraw = ImageDraw.Draw(glow)
  gdraw.ellipse([70, 140, 1010, 780], fill=(255, 236, 150, 115))
  gdraw.ellipse([110, 820, 930, 1560], fill=(255, 215, 110, 80))
  glow = glow.filter(ImageFilter.GaussianBlur(75))
  return Image.alpha_composite(base.convert("RGBA"), glow).convert("RGB")


def draw_glow_card(
    canvas_rgba: Image.Image,
    box: list[int],
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    glow_color: tuple[int, int, int, int],
    width: int = 6,
):
  # Soft outer glow
  glow = Image.new("RGBA", canvas_rgba.size, (0, 0, 0, 0))
  gdraw = ImageDraw.Draw(glow)
  gx1, gy1, gx2, gy2 = box[0] - 10, box[1] - 10, box[2] + 10, box[3] + 10
  gdraw.rounded_rectangle(
      [gx1, gy1, gx2, gy2], radius=radius + 8, fill=glow_color
  )
  glow = glow.filter(ImageFilter.GaussianBlur(18))
  canvas_rgba.alpha_composite(glow)

  # Subtle drop shadow
  shadow = Image.new("RGBA", canvas_rgba.size, (0, 0, 0, 0))
  sdraw = ImageDraw.Draw(shadow)
  sdraw.rounded_rectangle(
      [box[0] + 5, box[1] + 9, box[2] + 5, box[3] + 9],
      radius=radius,
      fill=(0, 0, 0, 65),
  )
  shadow = shadow.filter(ImageFilter.GaussianBlur(8))
  canvas_rgba.alpha_composite(shadow)

  # Main crisp card
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
  bg = make_glowing_background().convert("RGBA")

  q_font = get_urdu_font(74)
  opt_font = get_urdu_font(58)
  ans_font = get_urdu_font(50)
  badge_font = get_latin_font(54)
  timer_font = get_latin_font(72)

  # Top glowing white question card
  draw_glow_card(
      bg,
      [54, 195, 1026, 655],
      radius=44,
      fill=(255, 253, 246, 255),
      outline=(25, 35, 55, 255),
      glow_color=(255, 240, 165, 120),
      width=6,
  )
  tdraw = ImageDraw.Draw(bg)
  q_shaped = urdu_text(item["question"])
  # Slight double-stroke for extra bold readability
  for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
    tdraw.multiline_text(
        (540 + dx, 425 + dy),
        q_shaped,
        fill=(12, 16, 24, 255),
        font=q_font,
        anchor="mm",
        align="center",
        spacing=22,
    )
  tdraw.multiline_text(
      (540, 425),
      q_shaped,
      fill=(10, 14, 22, 255),
      font=q_font,
      anchor="mm",
      align="center",
      spacing=22,
  )

  # 3 glowing option cards (A, B, C)
  start_y = 700
  row_h = 215
  gap = 26
  correct_idx = item.get("correct_index", 0)

  for idx, (_, _, label) in enumerate(item["options"][:3]):
    y1 = start_y + idx * (row_h + gap)
    y2 = y1 + row_h
    is_win = show_answer and (idx == correct_idx)

    fill_col = (212, 255, 226, 255) if is_win else (255, 254, 250, 255)
    out_col = (12, 155, 68, 255) if is_win else (28, 72, 195, 255)
    glow_col = (45, 235, 115, 155) if is_win else (255, 235, 155, 95)
    b_w = 8 if is_win else 6

    draw_glow_card(
        bg,
        [54, y1, 895, y2],
        radius=34,
        fill=fill_col,
        outline=out_col,
        glow_color=glow_col,
        width=b_w,
    )

    row_draw = ImageDraw.Draw(bg)
    badge_letter = f"{['A', 'B', 'C'][idx]})"
    b_fill = (16, 140, 62) if is_win else (242, 246, 255)
    b_fg = (255, 255, 255) if is_win else (15, 20, 35)

    row_draw.rounded_rectangle(
        [72, y1 + 20, 192, y2 - 20],
        radius=22,
        fill=b_fill,
        outline=(20, 25, 40),
        width=4,
    )
    row_draw.text(
        (132, y1 + row_h // 2),
        badge_letter,
        fill=b_fg,
        font=badge_font,
        anchor="mm",
    )

    photo = fit_photo(thumb_paths[idx], 230, row_h - 34)
    row_draw.rounded_rectangle(
        [204, y1 + 15, 438, y2 - 15],
        radius=20,
        fill=(255, 255, 255),
        outline=(30, 40, 60),
        width=3,
    )
    bg.paste(photo, (206, y1 + 17))

    opt_shaped = urdu_text(label)
    for dx, dy in [(-1, 0), (1, 0)]:
      row_draw.text(
          (868 + dx, y1 + row_h // 2 + dy),
          opt_shaped,
          fill=(12, 16, 24, 255),
          font=opt_font,
          anchor="rm",
      )
    row_draw.text(
        (868, y1 + row_h // 2),
        opt_shaped,
        fill=(10, 14, 22, 255),
        font=opt_font,
        anchor="rm",
    )

  # 5-second glowing countdown badge
  if timer_num is not None and not show_answer:
    draw_glow_card(
        bg,
        [385, 1445, 565, 1575],
        radius=36,
        fill=(20, 24, 38, 255),
        outline=(255, 215, 65, 255),
        glow_color=(255, 210, 55, 165),
        width=6,
    )
    fdraw = ImageDraw.Draw(bg)
    fdraw.text(
        (475, 1510),
        str(timer_num),
        fill=(255, 228, 80, 255),
        font=timer_font,
        anchor="mm",
    )

  # Answer banner positioned cleanly above Shorts bottom metadata
  if show_answer and item.get("answer_label"):
    draw_glow_card(
        bg,
        [54, 1445, 895, 1575],
        radius=32,
        fill=(12, 118, 56, 255),
        outline=(255, 250, 210, 255),
        glow_color=(50, 235, 120, 165),
        width=6,
    )
    fdraw = ImageDraw.Draw(bg)
    ans_shaped = urdu_text(item["answer_label"])
    for dx, dy in [(-1, 0), (1, 0)]:
      fdraw.text(
          (475 + dx, 1510 + dy),
          ans_shaped,
          fill=(255, 255, 255, 255),
          font=ans_font,
          anchor="mm",
      )
    fdraw.text(
        (475, 1510),
        ans_shaped,
        fill=(255, 255, 255, 255),
        font=ans_font,
        anchor="mm",
    )

  bg.convert("RGB").save(out_png)
  return out_png


async def _tts_speak(text: str, out_mp3: str, rate: str = "+4%"):
  for voice in ["ur-PK-AsadNeural", "ur-PK-UzmaNeural"]:
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
  - 0.0s  .. 5.5s  : Question & options voice-over
  - 5.5s  .. 10.5s : Soft warm wooden 'tok-tok-tok' clock tick during 5s timer
  - 10.5s .. 11.3s : Final 'too' (teeeeeennnnnnn) tone
  - 11.4s .. 15.0s : Voice-over speaks the answer clearly
  """
  sr = 44100
  total_samples = int(PER_QUESTION_SEC * sr)
  samples = [0.0] * total_samples

  q_speech = item.get("question_speech", "")
  a_speech = item.get("answer_speech", item.get("answer_label", ""))
  base_name = os.path.basename(out_wav)

  if HAS_TTS and q_speech.strip():
    q_mp3 = os.path.join(work_dir, f"{base_name}_q.mp3")
    asyncio.run(_tts_speak(q_speech, q_mp3, rate="+6%"))
    _mix_mp3_into_samples(
        q_mp3, samples, 0.0, 5.4, sr, work_dir, f"{base_name}_q"
    )

  # Soft warm clock tick ('tok-tok') every 0.25s from 5.5s to 10.5s
  tick_t = 5.5
  while tick_t < 10.5:
    start_i = int(tick_t * sr)
    tick_len = int(0.045 * sr)
    for k in range(tick_len):
      idx = start_i + k
      if idx < total_samples:
        t_rel = k / sr
        env = math.exp(-k / (0.012 * sr))
        # Warm woody low-mid thud + gentle click
        wood = 0.26 * env * math.sin(2 * math.pi * 420 * t_rel)
        click = 0.12 * env * math.sin(2 * math.pi * 840 * t_rel)
        samples[idx] += wood + click
    tick_t += 0.25

  # Final 'too' (teeeeeennnnnnn) from 10.5s to 11.3s
  b_start = int(10.5 * sr)
  b_len = int(0.8 * sr)
  for k in range(b_len):
    idx = b_start + k
    if idx < total_samples:
      t_rel = k / sr
      fade_in = min(1.0, k / (0.015 * sr))
      fade_out = min(1.0, (b_len - k) / (0.06 * sr))
      tone = 0.30 * math.sin(2 * math.pi * 620 * t_rel) + 0.12 * math.sin(
          2 * math.pi * 1240 * t_rel
      )
      samples[idx] += tone * fade_in * fade_out

  # Spoken answer right after 'too' (11.4s to 15.0s)
  if HAS_TTS and a_speech.strip():
    a_mp3 = os.path.join(work_dir, f"{base_name}_a.mp3")
    asyncio.run(_tts_speak(a_speech, a_mp3, rate="+4%"))
    _mix_mp3_into_samples(
        a_mp3, samples, 11.4, 3.5, sr, work_dir, f"{base_name}_a"
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
    for o_idx, (_, photo_query, _) in enumerate(item["options"][:3]):
      p_file = os.path.join(work_dir, f"q{q_idx+1}_opt{o_idx+1}.jpg")
      thumb_paths.append(fetch_real_photo(photo_query, p_file))

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
