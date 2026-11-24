import json
import os
from google import genai


def _fallback_scenes(topic: str, num_scenes: int = 8) -> list[dict]:
  base_scenes = [
      {
          "scene": 1,
          "duration_sec": 7,
          "line": (
              "Aakhri zamana aayega to waqt aise guzrega jaise palak jhapakte"
              " hi din beet gaya."
          ),
          "action": (
              "A fast-moving modern clock beside a busy city street at dusk"
          ),
          "image_prompt": (
              "Dramatic 3D cartoon style illustration, glowing clock hands"
              " spinning fast over a crowded modern city street at twilight,"
              " cinematic lighting, 9:16 vertical, no text"
          ),
      },
      {
          "scene": 2,
          "duration_sec": 7,
          "line": (
              "Har haath mein screen hogi, par dil aapas mein door hotay"
              " jayenge."
          ),
          "action": (
              "People sitting close together staring silently at glowing phones"
              " in dim light"
          ),
          "image_prompt": (
              "Dramatic 3D cartoon style illustration, people sitting on a"
              " bench looking only at glowing phone screens with cold blue light"
              " and emotional distance, 9:16 vertical, no text"
          ),
      },
      {
          "scene": 3,
          "duration_sec": 8,
          "line": "Sach ko jhoot aur jhoot ko sach kehne ka daur aayega.",
          "action": (
              "A distorted mirror reflecting a false image while truth stands"
              " in shadow"
          ),
          "image_prompt": (
              "Dramatic 3D cartoon style illustration, a cracked ornate mirror"
              " showing a glowing illusion while a simple lantern of truth"
              " flickers beside it, moody lighting, 9:16 vertical, no text"
          ),
      },
      {
          "scene": 4,
          "duration_sec": 8,
          "line": (
              "Rishton mein sabr kam aur gussa zyada hoga, chhoti baat par"
              " dil tootenge."
          ),
          "action": (
              "A broken bridge or fractured glass reflecting a tense argument"
          ),
          "image_prompt": (
              "Dramatic 3D cartoon style illustration, shattered glass shards"
              " on a dark floor with warm and cold contrast symbolizing"
              " broken bonds and impatience, 9:16 vertical, no text"
          ),
      },
      {
          "scene": 5,
          "duration_sec": 7,
          "line": (
              "Fitnon ki aandhi mein sab se bari aazmaish apna imaan bachana"
              " hogi."
          ),
          "action": (
              "A lone traveler holding a small glowing flame against strong"
              " wind"
          ),
          "image_prompt": (
              "Dramatic 3D cartoon style illustration, a lone traveler"
              " cupping a small warm flame with both hands against dark swirling"
              " wind, cinematic 3D render, 9:16 vertical, no text"
          ),
      },
      {
          "scene": 6,
          "duration_sec": 8,
          "line": (
              "Jis ne andheray mein roshni thami rakhi, wahi asal kamyab"
              " tehra."
          ),
          "action": (
              "Footsteps walking steadily along a narrow path toward dawn light"
          ),
          "image_prompt": (
              "Dramatic 3D cartoon style illustration, a narrow winding path"
              " leading from dark storm clouds toward golden morning horizon"
              " rays, 9:16 vertical, no text"
          ),
      },
      {
          "scene": 7,
          "duration_sec": 7,
          "line": (
              "Zaban sambhalo, niyat saaf rakho, aur har haal mein Allah par"
              " bharosa karo."
          ),
          "action": (
              "A calm person sitting quietly in prayerful reflection at night"
          ),
          "image_prompt": (
              "Dramatic 3D cartoon style illustration, a peaceful young man"
              " sitting quietly in a dimly lit room with soft moonlight"
              " streaming through a window, 9:16 vertical, no text"
          ),
      },
      {
          "scene": 8,
          "duration_sec": 8,
          "line": (
              "Aakhri zamana khauf ka nahi, bedari aur imaan mazboot karne ka"
              " waqt hai."
          ),
          "action": (
              "Sunrise breaking over a calm horizon with a bright guiding star"
          ),
          "image_prompt": (
              "Dramatic 3D cartoon style illustration, first light of dawn"
              " rising over quiet hills with a bright star in the sky, hopeful"
              " cinematic tone, 9:16 vertical, no text"
          ),
      },
  ]
  return base_scenes[:num_scenes]


def generate_cartoon_script_60s(
    topic: str, num_scenes: int = 8
) -> list[dict]:
  api_key = os.environ.get("GEMINI_API_KEY", "").strip()
  if not api_key:
    return _fallback_scenes(topic, num_scenes)

  prompt = f"""
Create a {num_scenes}-scene script for a 60-second vertical cartoon short in Roman Urdu on the topic:
"{topic}"

Total duration across all {num_scenes} scenes should be around 58 to 60 seconds.
Return ONLY a valid JSON list of objects. Each object must have:
- "scene": integer (1 to {num_scenes})
- "duration_sec": integer (between 6 and 8)
- "line": short impactful Roman Urdu narration/caption line (max 14 words)
- "action": concise visual action description
- "image_prompt": detailed English prompt for a dramatic 3D cartoon scene (9:16 vertical, no text in image)
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
    data = json.loads(raw)
    if isinstance(data, list) and len(data) >= 4:
      return data[:num_scenes]
  except Exception as exc:
    print(f"Gemini script fallback triggered: {exc}")

  return _fallback_scenes(topic, num_scenes)
