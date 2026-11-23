import os
import json
from google import genai


def generate_cartoon_script_60s(topic: str, num_scenes: int = 8) -> list[dict]:
  prompt = f"""
    Create a ~60-second animated comedy script for the topic: "{topic}".
    Split it into {num_scenes} scenes so total duration is around 60 seconds.
    Keep pacing lively with clear setup, escalation, twist, and punchline.
    Return ONLY a valid JSON list of objects with keys:
    - "scene": integer (1 to {num_scenes})
    - "duration_sec": integer (typically 6 to 8, summing close to 60)
    - "action": short description of movement, expression, or slapstick beat
    - "line": short spoken line or sound/action cue
    - "image_prompt": clean 2D cartoon illustration prompt for this moment
    """

  client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
  response = client.models.generate_content(
      model="gemini-2.5-flash",
      contents=prompt,
  )

  raw_text = response.text.strip()
  if raw_text.startswith("```"):
    raw_text = raw_text.strip("`").replace("json", "", 1).strip()

  return json.loads(raw_text)


if __name__ == "__main__":
  script = generate_cartoon_script_60s(
      "Two friends trying to sneak a giant burger in class without getting caught",
      8,
  )
  print(json.dumps(script, indent=2, ensure_ascii=False))
