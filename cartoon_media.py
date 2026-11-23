import os
import json
import requests
from urllib.parse import quote


def fetch_pixabay_image(
    query: str, api_key: str, out_path: str
) -> str | None:
  clean_query = quote(" ".join(query.split()[:4]))
  url = (
      f"https://pixabay.com/api/?key={api_key}"
      f"&q={clean_query}&image_type=illustration&safesearch=true&per_page=3"
  )
  try:
    res = requests.get(url, timeout=20)
    res.raise_for_status()
    hits = res.json().get("hits", [])
    if not hits:
      return None

    img_url = hits[0].get("largeImageURL") or hits[0].get("webformatURL")
    if not img_url:
      return None

    img_data = requests.get(img_url, timeout=30)
    img_data.raise_for_status()
    with open(out_path, "wb") as f:
      f.write(img_data.content)
    return out_path
  except Exception as e:
    print(f"Pixabay fallback error for '{query}': {e}")
    return None


def generate_free_ai_image(prompt: str, out_path: str) -> str | None:
  """
    Yahan apni free AI image API/endpoint call lagayein.
    Agar quota khatam ho ya error aaye to None return karein
    taake Pixabay fallback ya image reuse chal sakay.
    """
  _ = (prompt, out_path)
  return None


def prepare_scene_media(
    scenes: list[dict],
    out_dir: str = "cartoon_assets",
    max_new_images: int = 4,
) -> list[dict]:
  os.makedirs(out_dir, exist_ok=True)
  pixabay_key = os.environ.get("PIXABAY_API_KEY", "").strip()
  generated_pool: list[str] = []
  updated_scenes: list[dict] = []

  for idx, scene in enumerate(scenes):
    scene_num = scene.get("scene", idx + 1)
    prompt = scene.get("image_prompt", "2d cartoon comedy scene")
    file_path = os.path.join(out_dir, f"scene_{scene_num:02d}.jpg")
    media_path = None

    if len(generated_pool) < max_new_images:
      media_path = generate_free_ai_image(prompt, file_path)

      if not media_path and pixabay_key:
        media_path = fetch_pixabay_image(prompt, pixabay_key, file_path)

      if media_path and os.path.exists(media_path):
        generated_pool.append(media_path)

    if not media_path and generated_pool:
      media_path = generated_pool[idx % len(generated_pool)]

    if not media_path:
      media_path = file_path

    scene_copy = dict(scene)
    scene_copy["image_path"] = media_path
    updated_scenes.append(scene_copy)

  return updated_scenes


if __name__ == "__main__":
  sample_scenes = [
      {
          "scene": 1,
          "duration_sec": 8,
          "image_prompt": "2d cartoon funny start",
      },
      {
          "scene": 2,
          "duration_sec": 7,
          "image_prompt": "2d cartoon comedy escalation",
      },
      {
          "scene": 3,
          "duration_sec": 8,
          "image_prompt": "2d cartoon twist reaction",
      },
      {
          "scene": 4,
          "duration_sec": 7,
          "image_prompt": "2d cartoon punchline ending",
      },
  ]
  print(
      json.dumps(
          prepare_scene_media(sample_scenes, max_new_images=4),
          indent=2,
          ensure_ascii=False,
      )
  )
