import os
import json
import shutil
import subprocess
from cartoon_script import generate_cartoon_script_60s
from cartoon_media import prepare_scene_media


def _escape_drawtext(text: str) -> str:
  cleaned = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
  cleaned = cleaned.replace("\n", " ").strip()
  return cleaned[:110]


def _find_font_path() -> str | None:
  candidates = [
      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
      "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
  ]
  for path in candidates:
    if os.path.exists(path):
      return path
  return None


def _auto_audio_filter(duration_sec: int, scene_idx: int) -> str:
  # Auto-generated soft rhythmic/chime bed at low volume (no external file needed)
  base_freq = 220 + (scene_idx % 4) * 55
  return (
      f"sine=frequency={base_freq}:sample_rate=44100:duration={duration_sec},"
      f"tremolo=f=3.5:d=0.6,volume=0.04,aformat=channel_layouts=stereo"
  )


def _render_scene_clip(
    image_path: str,
    duration_sec: int,
    caption_text: str,
    out_clip: str,
    scene_idx: int,
    width: int = 1080,
    height: int = 1920,
    fps: int = 24,
) -> bool:
  if not os.path.exists(image_path):
    return False

  total_frames = max(int(duration_sec * fps), fps * 2)
  if scene_idx % 2 == 0:
    zp = (
        f"zoompan=z='min(zoom+0.0012,1.25)'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s={width}x{height}:fps={fps}"
    )
  else:
    zp = (
        f"zoompan=z='1.15'"
        f":x='(iw-iw/zoom)*((on/{max(total_frames-1,1)}))'"
        f":y='ih/2-(ih/zoom/2)'"
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
    draw = (
        f"drawtext=text='{safe_caption}'{font_opt}"
        f":fontcolor=white:fontsize=44:box=1:boxcolor=black@0.65:boxborderw=14"
        f":x=(w-text_w)/2:y=h-280"
    )
    filters.append(draw)

  vf = ",".join(filters)
  af = _auto_audio_filter(duration_sec, scene_idx)

  cmd = [
      "ffmpeg",
      "-y",
      "-loop",
      "1",
      "-i",
      image_path,
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
    print(f"Scene {scene_idx+1} render error: {res.stderr[-400:]}")
    return False
  return os.path.exists(out_clip)


def build_cartoon_video(
    scenes: list[dict],
    out_video: str = "cartoon_out.mp4",
    temp_dir: str = "cartoon_temp",
) -> str | None:
  if not shutil.which("ffmpeg"):
    print("FFmpeg not found in environment.")
    return None

  os.makedirs(temp_dir, exist_ok=True)
  clip_paths: list[str] = []

  for idx, scene in enumerate(scenes):
    dur = int(scene.get("duration_sec", 7) or 7)
    dur = max(4, min(dur, 12))
    img_path = scene.get("image_path", "")
    caption = scene.get("line") or scene.get("action") or ""
    clip_file = os.path.join(temp_dir, f"clip_{idx+1:02d}.mp4")

    if _render_scene_clip(img_path, dur, caption, clip_file, idx):
      clip_paths.append(clip_file)

  if not clip_paths:
    print("No scene clips rendered.")
    return None

  concat_list = os.path.join(temp_dir, "clips.txt")
  with open(concat_list, "w", encoding="utf-8") as f:
    for cp in clip_paths:
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
      concat_list,
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
      out_video,
  ]
  res = subprocess.run(cmd, capture_output=True, text=True)
  if res.returncode != 0:
    print(f"Final concat error: {res.stderr[-400:]}")
    return None

  return out_video if os.path.exists(out_video) else None


if __name__ == "__main__":
  topic = (
      "Two funny friends trying to eat the last samosa in a quiet room"
      " without getting caught"
  )
  script_scenes = generate_cartoon_script_60s(topic, num_scenes=8)
  media_scenes = prepare_scene_media(
      script_scenes, out_dir="cartoon_assets", max_new_images=4
  )
  print(json.dumps(media_scenes, indent=2, ensure_ascii=False))
  out = build_cartoon_video(media_scenes, out_video="cartoon_out.mp4")
  print("Output video:", out)
