import json
import os
import re
import shutil
import subprocess
from urllib.parse import quote
import requests

try:
  from google import genai
except ImportError:
  genai = None


def _clean_text(text: str, max_len: int = 120) -> str:
  cleaned = re.sub(r"\s+", " ", (text or "")).strip()
  return cleaned[:max_len]


def _escape_drawtext(text: str) -> str:
  cleaned = _clean_text(text, max_len=110)
  return (
      cleaned.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
  )


def _find_font_path() -> str | None:
  candidates = [
      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
      "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
  ]
  for path in candidates:
    if os.path.exists(path):
      return path
  return None


def _default_clips(topic: str, num_clips: int = 12) -> list[dict]:
  base = [
      {
          "clip": 1,
          "duration_sec": 4,
          "line": (
              "Aakhri zamana aayega to waqt aise guzrega jaise palak jhapakte"
              " hi din beet gaya."
          ),
          "visual": "fast clock and busy evening city street",
      },
      {
          "clip": 2,
          "duration_sec": 4,
          "line": (
              "Har haath mein screen hogi, par dil aapas mein door hotay"
              " jayenge."
          ),
          "visual": "people looking at glowing phone screens in low light",
      },
      {
          "clip": 3,
          "duration_sec": 4,
          "line": "Sach aur jhoot ke darmiyan farq dhundla parne lagega.",
          "visual": "shadow and light contrast in a quiet alley",
      },
      {
          "clip": 4,
          "duration_sec": 4,
          "line": "Baaton mein sakhti aur sabr mein kami aam ho jayegi.",
          "visual": "storm clouds gathering over quiet rooftops",
      },
      {
          "clip": 5,
          "duration_sec": 4,
          "line": (
              "Fitnon ki aandhi mein sab se bari aazmaish apna imaan bachana"
              " hogi."
          ),
          "visual": "small warm light glowing against dark wind",
      },
      {
          "clip": 6,
          "duration_sec": 4,
          "line": (
              "Jis ne andheray mein roshni thami rakhi, wahi asal kamyab"
              " tehra."
          ),
          "visual": "footsteps walking steadily toward morning light",
      },
      {
          "clip": 7,
          "duration_sec": 4,
          "line": (
              "Zaban sambhalo, niyat saaf rakho, aur har haal mein Allah par"
              " bharosa karo."
          ),
          "visual": "calm night sky with quiet stars",
      },
      {
          "clip": 8,
          "duration_sec": 4,
          "line": (
              "Aakhri zamana khauf ka nahi, bedari aur imaan mazboot karne ka"
              " waqt hai."
          ),
          "visual": "dawn breaking over peaceful horizon",
      },
      {
          "clip": 9,
          "duration_sec": 4,
          "line": "Har amal chhota nahi hota jab us ke peeche ikhlas ho.",
          "visual": "soft golden rays over calm water",
      },
      {
          "clip": 10,
          "duration_sec": 4,
          "line": "Toba aur astaghfar dil ki sakhti ko narm kar dete hain.",
          "visual": "raindrops falling gently on dark surface",
      },
      {
          "clip": 11,
          "duration_sec": 4,
          "line": "Sacha insaan wahi hai jo mushkil mein bhi haq ka saath na chhore.",
          "visual": "steady lantern in twilight",
      },
      {
          "clip": 12,
          "duration_sec": 4,
          "line": "Apni aakirat aur amal ko aaj hi durust kar lo.",
          "visual": "sunrise illuminating open sky",
      },
  ]
  if num_clips <= len(base):
    return base[:num_clips]

  expanded = list(base)
  while len(expanded) < num_clips:
    idx = len(expanded) + 1
    expanded.append({
        "clip": idx,
        "duration_sec": 4,
        "line": _clean_text(f"{topic} — imaan, sabr aur amal ki roshni.", 100),
        "visual": "peaceful sky and light",
    })
  return expanded


def generate_script_clips(topic: str, num_clips: int = 12) -> list[dict]:
  api_key = os.environ.get("GEMINI_API_KEY", "").strip()
  if not api_key or genai is None:
    return _default_clips(topic, num_clips)

  prompt = f"""
Create a {num_clips}-clip script in Roman Urdu for a vertical short video on:
"{topic}"

Return ONLY a valid JSON list of {num_clips} objects.
Each object must contain:
- "clip": integer (1 to {num_clips})
- "duration_sec": integer (between 3 and 5)
- "line": short Roman Urdu line (max 14 words)
- "visual": short English visual search phrase (no text)
"""

  try:
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    raw = (response.text or "").strip()
    if raw.startswith("```"):
      raw = raw.strip("`")
      if raw.startswith("json"):
        raw = raw[4:].strip()
    parsed = json.loads(raw)
    if isinstance(parsed, list) and len(parsed) >= 6:
      return parsed[:num_clips]
  except Exception as exc:
    print(f"Gemini script fallback used: {exc}")

  return _default_clips(topic, num_clips)


def _download_image_for_clip(
    visual_query: str, out_path: str, idx: int
) -> bool:
  clean_q = re.sub(r"[^A-Za-z0-9 ,-]", " ", visual_query or "calm sky")
  clean_q = re.sub(r"\s+", " ", clean_q).strip() or "calm sky"

  pixabay_key = os.environ.get("PIXABAY_API_KEY", "").strip()
  if pixabay_key:
    try:
      pixabay_url = "[https://pixabay.com/api/](https://pixabay.com/api/)"
      resp = requests.get(
          pixabay_url,
          params={
              "key": pixabay_key,
              "q": clean_q[:80],
              "image_type": "photo",
              "per_page": 5,
              "safesearch": "true",
          },
          timeout=20,
      )
      resp.raise_for_status()
      hits = resp.json().get("hits", [])
      if hits:
        hit = hits[idx % len(hits)]
        img_url = hit.get("largeImageURL") or hit.get("webformatURL")
        if isinstance(img_url, str) and img_url.startswith("http"):
          img_resp = requests.get(img_url.strip(), timeout=25)
          img_resp.raise_for_status()
          with open(out_path, "wb") as f:
            f.write(img_resp.content)
          if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return True
    except Exception as exc:
      print(f"Pixabay image error ({out_path}): {exc}")

  try:
    safe_q = quote(clean_q[:60])
    pollinations_url = (
        f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){safe_q}"
        "?width=1080&height=1920&nologo=true"
    )
    img_resp = requests.get(pollinations_url, timeout=30)
    img_resp.raise_for_status()
    with open(out_path, "wb") as f:
      f.write(img_resp.content)
    return os.path.exists(out_path) and os.path.getsize(out_path) > 1000
  except Exception as exc:
    print(f"Fallback image error ({out_path}): {exc}")
    return False


def _render_clip(
    image_path: str,
    duration_sec: int,
    caption_text: str,
    out_clip: str,
    clip_idx: int,
    width: int = 1080,
    height: int = 1920,
    fps: int = 24,
) -> bool:
  total_frames = max(int(duration_sec * fps), fps * 2)
  mode = clip_idx % 3
  if mode == 0:
    zp = (
        f"zoompan=z='min(zoom+0.0015,1.25)'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s={width}x{height}:fps={fps}"
    )
  elif mode == 1:
    zp = (
        f"zoompan=z='1.15'"
        f":x='(iw-iw/zoom)*((on/{max(total_frames-1,1)}))'"
        f":y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s={width}x{height}:fps={fps}"
    )
  else:
    zp = (
        f"zoompan=z='max(1.22-0.0012*on,1.02)'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s={width}x{height}:fps={fps}"
    )

  filters = [
      f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase",
      zp,
      "format=yuv420p",
  ]

  safe_caption = _escape_drawtext(caption_text)
  if safe_caption:
    font_path = _find_font_path()
    font_opt = f":fontfile='{font_path}'" if font_path else ""
    filters.append(
        f"drawtext=text='{safe_caption}'{font_opt}"
        f":fontcolor=white:fontsize=42:box=1:boxcolor=black@0.65:boxborderw=14"
        f":x=(w-text_w)/2:y=h-300"
    )

  vf = ",".join(filters)
  freq = 196 + (clip_idx % 4) * 36
  af = (
      f"sine=frequency={freq}:sample_rate=44100:duration={duration_sec},"
      f"tremolo=f=2.2:d=0.4,volume=0.03,aformat=channel_layouts=stereo"
  )

  if os.path.exists(image_path):
    video_input = ["-loop", "1", "-i", image_path]
  else:
    video_input = ["-f", "lavfi", "-i", f"color=c=#141824:s={width}x{height}:r={fps}"]

  cmd = [
      "ffmpeg",
      "-y",
      *video_input,
      "-f",
      "lavfi",
      "-i",
      af,
      "-vf",
      vf,
      "-t",
      str(duration_sec),
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-crf",
      "24",
      "-c:a",
      "aac",
      "-b:a",
      "128k",
      "-shortest",
      out_clip,
  ]

  res = subprocess.run(cmd, capture_output=True, text=True)
  if res.returncode != 0:
    print(f"Clip {clip_idx+1} error: {res.stderr[-400:]}")
    return False
  return os.path.exists(out_clip)


def build_reel(
    topic: str,
    out_path: str = "final_islamic_short.mp4",
    temp_dir: str = "reel_temp",
) -> str | None:
  if not shutil.which("ffmpeg"):
    print("FFmpeg not found.")
    return None

  os.makedirs(temp_dir, exist_ok=True)
  clips = generate_script_clips(topic, num_clips=12)
  rendered_clips: list[str] = []

  for idx, item in enumerate(clips):
    dur = int(item.get("duration_sec", 4) or 4)
    dur = max(3, min(dur, 8))
    visual = item.get("visual") or "calm sky and light"
    line = item.get("line") or topic

    img_file = os.path.join(temp_dir, f"img_{idx+1:02d}.jpg")
    clip_file = os.path.join(temp_dir, f"clip_{idx+1:02d}.mp4")

    _download_image_for_clip(visual, img_file, idx)
    if _render_clip(img_file, dur, line, clip_file, idx):
      rendered_clips.append(clip_file)

  if not rendered_clips:
    print("No clips rendered.")
    return None

  list_file = os.path.join(temp_dir, "concat_list.txt")
  with open(list_file, "w", encoding="utf-8") as f:
    for cp in rendered_clips:
      abs_cp = os.path.abspath(cp).replace("\\", "/")
      f.write(f"file '{abs_cp}'\n")

  cmd = [
      "ffmpeg",
      "-y",
      "-f",
      "concat",
      "-safe",
      "0",
      "-i",
      list_file,
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-crf",
      "23",
      "-c:a",
      "aac",
      "-b:a",
      "128k",
      out_path,
  ]
  res = subprocess.run(cmd, capture_output=True, text=True)
  if res.returncode != 0:
    print(f"Final concat error: {res.stderr[-400:]}")
    return None

  if os.path.exists(out_path):
    shutil.copyfile(out_path, "islamic_reel_out.mp4")
    return out_path

  return None


if __name__ == "__main__":
  topic = os.environ.get(
      "CARTOON_TOPIC",
      "Aakhri zamana ki nishaniyan, fitne aur imaan bachane ki ahmiyat",
  )
  output = build_reel(topic, out_path="final_islamic_short.mp4")
  print("Output:", output)
