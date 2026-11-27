import asyncio
import json
import os
import subprocess
from urllib.parse import quote
from PIL import Image, ImageDraw, ImageFont
import requests

try:
  import arabic_reshaper
  from bidi.algorithm import get_display

  HAS_RESHAPE = True
except ImportError:
  HAS_RESHAPE = False

try:
  import edge_tts

  HAS_TTS = True
except ImportError:
  HAS_TTS = False

W, H = 1080, 1920
TOTAL_DURATION = 18
SEG_DURATION = 9
FINAL_MP4 = "final_islamic_short.mp4"
HISTORY_FILE = "islamic_history.json"

FALLBACK_QUIZ_18S = [
    {
        "question": "اللہ اپنے بندے سے\nکب سب سے زیادہ\nخوش ہوتا ہے؟",
        "options": [
            ("A)", "bed room", "جب وہ سوتا ہے"),
            ("B)", "football", "جب وہ کھیلتا ہے"),
            ("C)", "mosque quran", "جب وہ توبہ کرتا ہے"),
        ],
        "correct_index": 2,
        "answer_label": "درست جواب: C",
        "narration": (
            "اللہ اپنے بندے سے کب سب سے زیادہ خوش ہوتا ہے؟ "
            "جب وہ سوتا ہے، کھیلتا ہے، یا توبہ کرتا ہے؟ "
            "درست جواب ہے: جب وہ توبہ کرتا ہے۔"
        ),
    },
    {
        "question": "اسلام کی سب سے پہلی\nمسجد کون سی ہے؟",
        "options": [
            ("A)", "white mosque", "مسجدِ قبا"),
            ("B)", "green dome", "مسجدِ نبوی"),
            ("C)", "jerusalem mosque", "مسجدِ اقصیٰ"),
        ],
        "correct_index": 0,
        "answer_label": "درست جواب: A",
        "narration": (
            "اسلام کی سب سے پہلی مسجد کون سی ہے؟ "
            "مسجدِ قبا، مسجدِ نبوی، یا مسجدِ اقصیٰ؟ "
            "درست جواب ہے: مسجدِ قبا۔"
        ),
    },
]


def shape_urdu(text: str) -> str:
  if not text:
    return ""
  if HAS_RESHAPE:
    reshaper = arabic_reshaper.ArabicReshaper(
        configuration={"delete_harakat": False}
    )
    out_lines = []
    for line in text.split("\n"):
      s = line.strip()
      if not s:
        out_lines.append("")
        continue
      reshaped = reshaper.reshape(s)
      out_lines.append(get_display(reshaped))
    return "\n".join(out_lines)
  return text


def get_latin_font(size: int) -> ImageFont.FreeTypeFont:
  candidates = [
      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
  ]
  for p in candidates:
    if os.path.exists(p):
      return ImageFont.truetype(p, size)
  return ImageFont.load_default()


def get_urdu_font(size: int) -> ImageFont.FreeTypeFont:
  candidates = [
      "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
  ]
  for p in candidates:
    if os.path.exists(p):
      return ImageFont.truetype(p, size)
  return ImageFont.load_default()


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


def generate_gemini_quiz_18s() -> list[dict]:
  api_key = os.environ.get("GEMINI_API_KEY", "").strip()
  if not api_key:
    return FALLBACK_QUIZ_18S

  used_questions = load_history()[-25:]
  avoid_text = "\n".join(f"- {q}" for q in used_questions)

  prompt = f"""
Create exactly 2 short, clear Islamic quiz questions in Urdu for an 18-second YouTube Short (9 seconds each).
Keep every question to 2 short lines (max 4-5 Urdu words per line) and each option to 2-4 Urdu words.
Provide 3 options (A, B, C), correct_index (0, 1, or 2), 1-2 simple English words per option for Pixabay photo search, a short Urdu answer_label, and a natural Urdu narration sentence (around 7 seconds when spoken).
Avoid repeating these previous questions:
{avoid_text}

Return ONLY valid JSON list of 2 objects:
[
  {{
    "question": "سطر 1\\nسطر 2",
    "options": [
      ["A)", "simple english word", "مختصر آپشن 1"],
      ["B)", "simple english word", "مختصر آپشن 2"],
      ["C)", "simple english word", "مختصر آپشن 3"]
    ],
    "correct_index": 0,
    "answer_label": "درست جواب: A",
    "narration": "اردو جملہ"
  }}
]
"""
  url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
  payload = {"contents": [{"parts": [{"text": prompt}]}]}

  try:
    res = requests.post(url, json=payload, timeout=30)
    res.raise_for_status()
    raw_text = (
        res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    )
    if raw_text.startswith("```"):
      raw_text = raw_text.strip("`")
      if raw_text.startswith("json"):
        raw_text = raw_text[4:]
      raw_text = raw_text.strip()

    parsed = json.loads(raw_text)
    if isinstance(parsed, list) and len(parsed) >= 2:
      cleaned = []
      for item in parsed[:2]:
        opts = [
            (str(o[0]), str(o[1]), str(o[2])) for o in item.get("options", [])[:3]
        ]
        if len(opts) == 3 and item.get("question"):
          cleaned.append({
              "question": str(item["question"]),
              "options": opts,
              "correct_index": int(item.get("correct_index", 0)) % 3,
              "answer_label": str(item.get("answer_label", "")),
              "narration": str(item.get("narration", item["question"])),
          })
      if len(cleaned) == 2:
        return cleaned
  except Exception as e:
    print("Gemini quiz fallback:", e)

  return FALLBACK_QUIZ_18S


def download_pixabay_thumb(query: str, out_path: str) -> bool:
  api_key = os.environ.get("PIXABAY_API_KEY", "").strip()
  if not api_key or not query:
    return False
  try:
    q = quote(" ".join(query.split()[:3]))
    url = f"[https://pixabay.com/api/?key=](https://pixabay.com/api/?key=){api_key}&q={q}&image_type=photo&safesearch=true&per_page=3"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    hits = r.json().get("hits", [])
    if hits:
      img_url = hits[0].get("webformatURL") or hits[0].get("largeImageURL")
      if img_url:
        img_res = requests.get(img_url, timeout=25)
        img_res.raise_for_status()
        with open(out_path, "wb") as f:
          f.write(img_res.content)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 500
  except Exception as e:
    print("Pixabay thumb error:", query, e)
  return False


def make_styled_thumb(
    img_path: str | None,
    letter: str,
    target_w: int,
    target_h: int,
    idx: int,
) -> Image.Image:
  if img_path and os.path.exists(img_path):
    try:
      im = Image.open(img_path).convert("RGB")
      scale = max(target_w / im.width, target_h / im.height)
      nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
      im = im.resize((nw, nh), Image.Resampling.LANCZOS)
      left = max(0, (nw - target_w) // 2)
      top = max(0, (nh - target_h) // 2)
      return im.crop((left, top, left + target_w, top + target_h))
    except Exception:
      pass

  # Clean fallback badge tile if no photo is available
  palette = [(232, 240, 255), (255, 244, 224), (232, 248, 238)]
  tile = Image.new("RGB", (target_w, target_h), palette[idx % len(palette)])
  d = ImageDraw.Draw(tile)
  d.rectangle([0, 0, target_w - 1, target_h - 1], outline=(180, 185, 195), width=2)
  f = get_latin_font(56)
  clean_letter = letter.replace(")", "").strip() or str(idx + 1)
  d.text(
      (target_w // 2, target_h // 2),
      clean_letter,
      fill=(45, 55, 75),
      font=f,
      anchor="mm",
  )
  return tile


def render_question_frame(
    item: dict,
    thumb_paths: list[str | None],
    out_png: str,
    highlight_answer: bool = False,
) -> str:
  img = Image.new("RGB", (W, H), (226, 176, 92))
  draw = ImageDraw.Draw(img)

  q_font = get_urdu_font(58)
  badge_font = get_latin_font(48)
  opt_font = get_urdu_font(44)
  ans_font = get_urdu_font(40)

  # Top rounded white question card
  draw.rounded_rectangle(
      [60, 240, 1020, 730],
      radius=38,
      fill=(255, 255, 255),
      outline=(20, 20, 20),
      width=5,
  )
  draw.multiline_text(
      (540, 485),
      shape_urdu(item["question"]),
      fill=(15, 15, 15),
      font=q_font,
      anchor="mm",
      align="center",
      spacing=18,
  )

  # A, B, C horizontal rows (kept clear of right-side Shorts icons)
  start_y = 780
  row_h = 230
  gap = 32
  correct_idx = item.get("correct_index", 0)

  for idx, (letter, _, label) in enumerate(item["options"][:3]):
    y1 = start_y + idx * (row_h + gap)
    y2 = y1 + row_h
    is_correct = highlight_answer and (idx == correct_idx)

    border_color = (22, 145, 72) if is_correct else (35, 75, 190)
    card_bg = (232, 252, 238) if is_correct else (255, 255, 255)
    border_w = 8 if is_correct else 5

    draw.rounded_rectangle(
        [60, y1, 900, y2],
        radius=28,
        fill=card_bg,
        outline=border_color,
        width=border_w,
    )

    # Left A/B/C badge using Latin font
    badge_txt = f"{['A', 'B', 'C'][idx]})"
    draw.rounded_rectangle(
        [78, y1 + 24, 198, y2 - 24],
        radius=16,
        fill=(25, 130, 65) if is_correct else (245, 245, 245),
        outline=(20, 20, 20),
        width=4,
    )
    draw.text(
        (138, y1 + row_h // 2),
        badge_txt,
        fill=(255, 255, 255) if is_correct else (15, 15, 15),
        font=badge_font,
        anchor="mm",
    )

    # Thumbnail image
    thumb = make_styled_thumb(thumb_paths[idx], badge_txt, 220, row_h - 40, idx)
    img.paste(thumb, (216, y1 + 20))

    # Right Urdu option label
    draw.text(
        (872, y1 + row_h // 2),
        shape_urdu(label),
        fill=(15, 15, 15),
        font=opt_font,
        anchor="rm",
    )

  if highlight_answer and item.get("answer_label"):
    draw.rounded_rectangle(
        [60, 1565, 900, 1665],
        radius=24,
        fill=(14, 92, 48),
        outline=(255, 255, 255),
        width=4,
    )
    draw.text(
        (480, 1615),
        shape_urdu(item["answer_label"]),
        fill=(255, 255, 255),
        font=ans_font,
        anchor="mm",
    )

  img.save(out_png)
  return out_png


async def _tts_save(text: str, out_mp3: str, voice: str = "ur-PK-AsadNeural"):
  communicate = edge_tts.Communicate(text, voice=voice, rate="+15%")
  await communicate.save(out_mp3)


def make_narration_segment(
    text: str, out_wav: str, target_sec: int = SEG_DURATION
) -> str:
  temp_mp3 = out_wav + ".mp3"
  generated_mp3 = False

  if HAS_TTS and text.strip():
    try:
      asyncio.run(_tts_save(text, temp_mp3))
      generated_mp3 = os.path.exists(temp_mp3) and os.path.getsize(temp_mp3) > 0
    except Exception as e:
      print("Edge TTS fallback:", e)

  if generated_mp3:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            temp_mp3,
            "-af",
            f"apad=whole_dur={target_sec}",
            "-t",
            str(target_sec),
            "-ar",
            "44100",
            "-ac",
            "2",
            out_wav,
        ],
        check=True,
    )
  else:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            str(target_sec),
            out_wav,
        ],
        check=True,
    )
  return out_wav


def main():
  work_dir = "quiz_build"
  os.makedirs(work_dir, exist_ok=True)

  quiz_items = generate_gemini_quiz_18s()
  video_clips = []
  audio_clips = []

  for q_idx, item in enumerate(quiz_items[:2]):
    thumb_paths: list[str | None] = []
    for o_idx, (_, query, _) in enumerate(item["options"][:3]):
      t_path = os.path.join(work_dir, f"q{q_idx+1}_opt{o_idx+1}.jpg")
      ok = download_pixabay_thumb(query, t_path)
      thumb_paths.append(t_path if ok else None)

    pre_png = os.path.join(work_dir, f"q{q_idx+1}_pre.png")
    ans_png = os.path.join(work_dir, f"q{q_idx+1}_ans.png")
    render_question_frame(item, thumb_paths, pre_png, highlight_answer=False)
    render_question_frame(item, thumb_paths, ans_png, highlight_answer=True)

    for tag, png_file, dur in [(
        "pre",
        pre_png,
        6,
    ), ("ans", ans_png, 3)]:
      seg_mp4 = os.path.join(work_dir, f"q{q_idx+1}_{tag}.mp4")
      subprocess.run(
          [
              "ffmpeg",
              "-y",
              "-loop",
              "1",
              "-i",
              png_file,
              "-t",
              str(dur),
              "-vf",
              f"scale={W}:{H},fps=30,format=yuv420p",
              "-c:v",
              "libx264",
              "-preset",
              "fast",
              "-crf",
              "23",
              seg_mp4,
          ],
          check=True,
      )
      video_clips.append(seg_mp4)

    seg_wav = os.path.join(work_dir, f"q{q_idx+1}_audio.wav")
    make_narration_segment(
        item.get("narration", ""), seg_wav, target_sec=SEG_DURATION
    )
    audio_clips.append(seg_wav)

  v_list = os.path.join(work_dir, "v_list.txt")
  with open(v_list, "w", encoding="utf-8") as f:
    for vc in video_clips:
      f.write(f"file '{os.path.abspath(vc)}'\n")

  merged_video = os.path.join(work_dir, "merged_v.mp4")
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
          merged_video,
      ],
      check=True,
  )

  a_list = os.path.join(work_dir, "a_list.txt")
  with open(a_list, "w", encoding="utf-8") as f:
    for ac in audio_clips:
      f.write(f"file '{os.path.abspath(ac)}'\n")

  merged_audio = os.path.join(work_dir, "merged_a.wav")
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
          merged_audio,
      ],
      check=True,
  )

  subprocess.run(
      [
          "ffmpeg",
          "-y",
          "-i",
          merged_video,
          "-i",
          merged_audio,
          "-t",
          str(TOTAL_DURATION),
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
  )

  save_history([x["question"] for x in quiz_items[:2]])
  print("Generated successfully:", FINAL_MP4)


if __name__ == "__main__":
  main()
