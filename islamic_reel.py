import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

try:
  import arabic_reshaper
  from bidi.algorithm import get_display

  HAS_BIDI = True
except ImportError:
  HAS_BIDI = False

W, H = 1080, 1920
TOTAL_DURATION = 18
SEG_DURATION = 9

DEFAULT_QUIZ_18S = [
    {
        "start": 0,
        "end": 9,
        "question": "اللہ اپنے بندے سے\nکب سب سے زیادہ\nخوش ہوتا ہے؟؟",
        "options": [
            ("A)", "opt_a.jpg", "جب وہ سوتا ہے"),
            ("B)", "opt_b.jpg", "جب وہ کھیلتا ہے"),
            ("C)", "opt_c.jpg", "جب وہ توبہ کرتا ہے"),
        ],
        "correct_index": 2,
        "answer_label": "درست جواب: C) جب وہ توبہ کرتا ہے",
    },
    {
        "start": 9,
        "end": 18,
        "question": "اسلام کی سب سے پہلی\nمسجد کون سی ہے؟",
        "options": [
            ("A)", "opt_a.jpg", "مسجدِ قبا"),
            ("B)", "opt_b.jpg", "مسجدِ نبوی"),
            ("C)", "opt_c.jpg", "مسجدِ اقصیٰ"),
        ],
        "correct_index": 0,
        "answer_label": "درست جواب: A) مسجدِ قبا",
    },
]


def shape_urdu(text: str) -> str:
  if not text:
    return ""
  if HAS_BIDI:
    lines = text.split("\n")
    shaped = [
        get_display(arabic_reshaper.reshape(line)) if line.strip() else ""
        for line in lines
    ]
    return "\n".join(shaped)
  return text


def find_font(size: int) -> ImageFont.FreeTypeFont:
  candidates = [
      "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
      "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
  ]
  for path in candidates:
    if os.path.exists(path):
      return ImageFont.truetype(path, size)
  return ImageFont.load_default()


def load_thumb(thumb_path: str, target_w: int, target_h: int) -> Image.Image:
  if thumb_path and os.path.exists(thumb_path):
    im = Image.open(thumb_path).convert("RGB")
    scale = max(target_w / im.width, target_h / im.height)
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - target_w) // 2)
    top = max(0, (nh - target_h) // 2)
    return im.crop((left, top, left + target_w, top + target_h))
  placeholder = Image.new("RGB", (target_w, target_h), (235, 230, 220))
  return placeholder


def render_question_frame(
    item: dict, out_png: str, highlight_answer: bool = False
) -> str:
  img = Image.new("RGB", (W, H), (226, 176, 92))
  draw = ImageDraw.Draw(img)

  q_font = find_font(62)
  badge_font = find_font(50)
  opt_font = find_font(46)
  ans_font = find_font(42)

  # Top rounded white question box
  draw.rounded_rectangle(
      [60, 250, 1020, 740],
      radius=38,
      fill=(255, 255, 255),
      outline=(20, 20, 20),
      width=5,
  )
  draw.multiline_text(
      (540, 495),
      shape_urdu(item["question"]),
      fill=(15, 15, 15),
      font=q_font,
      anchor="mm",
      align="center",
      spacing=14,
  )

  # A, B, C horizontal cards (kept left of right-side Shorts buttons)
  start_y = 790
  row_h = 235
  gap = 32
  correct_idx = item.get("correct_index", 0)

  for idx, (letter, thumb_path, label) in enumerate(item["options"][:3]):
    y1 = start_y + idx * (row_h + gap)
    y2 = y1 + row_h
    is_correct = highlight_answer and (idx == correct_idx)

    border_color = (22, 145, 72) if is_correct else (35, 75, 190)
    card_bg = (232, 252, 238) if is_correct else (255, 255, 255)
    border_w = 8 if is_correct else 5

    draw.rounded_rectangle(
        [60, y1, 910, y2],
        radius=28,
        fill=card_bg,
        outline=border_color,
        width=border_w,
    )

    # Left A/B/C badge
    draw.rounded_rectangle(
        [80, y1 + 24, 205, y2 - 24],
        radius=16,
        fill=(25, 130, 65) if is_correct else (245, 245, 245),
        outline=(20, 20, 20),
        width=4,
    )
    draw.text(
        (142, y1 + row_h // 2),
        letter,
        fill=(255, 255, 255) if is_correct else (15, 15, 15),
        font=badge_font,
        anchor="mm",
    )

    # Thumbnail image
    thumb_w, thumb_h = 230, row_h - 40
    thumb = load_thumb(thumb_path, thumb_w, thumb_h)
    img.paste(thumb, (225, y1 + 20))

    # Right Urdu option label
    draw.text(
        (880, y1 + row_h // 2),
        shape_urdu(label),
        fill=(15, 15, 15),
        font=opt_font,
        anchor="rm",
    )

  # Answer banner in last 3 seconds of each question
  if highlight_answer and item.get("answer_label"):
    draw.rounded_rectangle(
        [60, 1580, 910, 1685],
        radius=24,
        fill=(14, 92, 48),
        outline=(255, 255, 255),
        width=4,
    )
    draw.text(
        (485, 1632),
        shape_urdu(item["answer_label"]),
        fill=(255, 255, 255),
        font=ans_font,
        anchor="mm",
    )

  img.save(out_png)
  return out_png


def build_18s_video(
    segments: list[dict] = DEFAULT_QUIZ_18S,
    audio_path: str | None = None,
    out_mp4: str = "islamic_short_18s.mp4",
    work_dir: str = "quiz_frames",
):
  os.makedirs(work_dir, exist_ok=True)
  clips = []

  for i, seg in enumerate(segments[:2]):
    pre_png = os.path.join(work_dir, f"q{i+1}_pre.png")
    ans_png = os.path.join(work_dir, f"q{i+1}_ans.png")
    render_question_frame(seg, pre_png, highlight_answer=False)
    render_question_frame(seg, ans_png, highlight_answer=True)

    pre_mp4 = os.path.join(work_dir, f"q{i+1}_pre.mp4")
    ans_mp4 = os.path.join(work_dir, f"q{i+1}_ans.mp4")

    for src_png, dst_mp4, dur in [(pre_png, pre_mp4, 6), (ans_png, ans_mp4, 3)]:
      subprocess.run(
          [
              "ffmpeg",
              "-y",
              "-loop",
              "1",
              "-i",
              src_png,
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
              dst_mp4,
          ],
          check=True,
      )
      clips.append(dst_mp4)

  concat_list = os.path.join(work_dir, "list.txt")
  with open(concat_list, "w", encoding="utf-8") as f:
    for c in clips:
      f.write(f"file '{os.path.abspath(c)}'\n")

  merged_v = os.path.join(work_dir, "video_only.mp4")
  subprocess.run(
      [
          "ffmpeg",
          "-y",
          "-f",
          "concat",
          "-safe",
          "0",
          "-i",
          concat_list,
          "-c",
          "copy",
          merged_v,
      ],
      check=True,
  )

  if audio_path and os.path.exists(audio_path):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            merged_v,
            "-i",
            audio_path,
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
            out_mp4,
        ],
        check=True,
    )
  else:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            merged_v,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
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
            out_mp4,
        ],
        check=True,
    )

  print("Ready:", out_mp4)


if __name__ == "__main__":
  build_18s_video()
