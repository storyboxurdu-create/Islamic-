import asyncio
import json
import os
import random
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
import edge_tts

OUTPUT_VIDEO = Path("final_islamic_long.mp4")
OUTPUT_META = Path("long_meta.json")
OUTPUT_THUMBNAIL = Path("long_thumbnail.jpg")
HISTORY_FILE = Path("islamic_long_history.json")

STORY_TEXT = (
    "ایک پرانے شہر میں ایک نیک اور محنتی انسان رہتا تھا جو دن رات حلال روزی کمانے کی کوشش کرتا اور ہر حال میں اللہ کا شکر ادا کرتا تھا۔ "
    "ایک وقت ایسا آیا جب کاروبار میں سخت نقصان ہوا اور حالات بالکل بدل گئے، مگر اس کا دل امید اور یقین سے خالی نہیں ہوا۔ "
    "لوگوں نے مشورے دیے کہ شکوہ کرو یا راستہ بدلو، مگر اس نے صبر کا دامن تھامے رکھا۔ وہ جانتا تھا کہ ہر رات کے بعد صبح ضرور آتی ہے۔ "
    "تنہائی کے لمحوں میں وہ سجدے میں جا کر اپنے رب سے دعا کرتا اور دل کو سکون دیتا۔ اس نے کبھی کسی کا حق نہیں مارا اور مشکل وقت میں بھی خیر خواہی کرتا رہا۔ "
    "رفتہ رفتہ حالات سنورنے لگے اور نئے دروازے کھل گئے۔ یہ واقعہ ہمیں سکھاتا ہے کہ صبر، اخلاص اور اللہ پر بھروسہ انسان کو ہر مشکل سے نکال کر کامیابی عطا کرتا ہے۔"
)

QUERIES = [
    "ancient stone city",
    "worker walking road",
    "dark stormy clouds",
    "candle light dark",
    "sunrise over horizon",
    "quiet night sky",
    "flowing river sunlight",
    "clear blue sky",
]


def get_dur(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
    )
    return float(out.strip())


async def make_tts(text: str, mp3_path: Path) -> None:
    voice = os.getenv("EDGE_TTS_VOICE", "").strip() or "ur-PK-AsadNeural"
    await edge_tts.Communicate(text=text, voice=voice, rate="-4%").save(str(mp3_path))


def fetch_clip(query: str, api_key: str, dest: Path, idx: int) -> Path:
    if api_key:
        url = f"https://pixabay.com/api/videos/?key={urllib.parse.quote(api_key)}&q={urllib.parse.quote(query)}&per_page=5&safesearch=true"
        try:
            data = json.loads(urllib.request.urlopen(url, timeout=15).read().decode("utf-8"))
            for hit in data.get("hits", []):
                vids = hit.get("videos", {})
                for k in ("medium", "small", "large", "tiny"):
                    link = (vids.get(k) or {}).get("url")
                    if link:
                        raw = dest.with_suffix(".raw.mp4")
                        urllib.request.urlretrieve(link, str(raw))
                        if raw.exists() and raw.stat().st_size > 30000:
                            subprocess.run(
                                ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(raw), "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,t=6,fps=30", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(dest)],
                                check=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                            return dest
        except Exception as e:
            print(f"Clip {idx} fallback: {e}")

    colors = ["0x0c1322", "0x151e30", "0x101827", "0x192236"]
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={colors[idx % 4]}:s=1080x1920:d=6", "-vf", "fps=30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(dest)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return dest


def main() -> None:
    work = Path("build_long_assets")
    work.mkdir(exist_ok=True)
    mp3 = work / "voice.mp3"
    wav = work / "voice.wav"
    asyncio.run(make_tts(STORY_TEXT, mp3))
    subprocess.run(["ffmpeg", "-y", "-i", str(mp3), "-ar", "44100", "-ac", "1", str(wav)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    dur = max(185.0, get_dur(wav))
    if get_dur(wav) < 185.0:
        pad = round(186.0 - get_dur(wav), 2)
        pw = work / "padded.wav"
        subprocess.run(["ffmpeg", "-y", "-i", str(wav), "-af", f"apad=pad_dur={pad}", "-ar", "44100", "-ac", "1", str(pw)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pw.replace(wav)
        dur = get_dur(wav)

    pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()
    clips = []
    for i in range(32):
        c = fetch_clip(QUERIES[i % len(QUERIES)], pixabay_key, work / f"c_{i:02d}.mp4", i)
        clips.append(c)

    concat_txt = work / "concat.txt"
    concat_txt.write_text("\n".join(f"file '{c.resolve()}'" for c in clips), encoding="utf-8")
    merged = work / "merged.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c:v", "copy", str(merged)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(merged), "-i", str(wav), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{dur}", str(OUTPUT_VIDEO)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(["ffmpeg", "-y", "-i", str(clips[0]), "-vframes", "1", str(OUTPUT_THUMBNAIL)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    meta = {
        "title": "سخت آزمائش میں صبر اور یقین کی سچی کہانی",
        "description": STORY_TEXT + "\n\n#Storybox #IslamicStory #UrduWaqiat",
        "tags": ["Islamic Story Urdu", "Urdu Waqiat", "Storybox"],
        "thumbnail_path": str(OUTPUT_THUMBNAIL),
        "video_path": str(OUTPUT_VIDEO),
    }
    OUTPUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    HISTORY_FILE.write_text(json.dumps({"used_ids": [f"run_{random.randint(100,999)}"]}, ensure_ascii=False), encoding="utf-8")
    print(f"Done: {OUTPUT_VIDEO} ({dur:.1f}s)")


if __name__ == "__main__":
    main()
