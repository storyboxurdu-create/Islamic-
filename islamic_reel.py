import asyncio
import json
import os
import subprocess
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

HISTORY_FILE = "islamic_history.json"
WORK_DIR = "build_islamic"
FINAL_VIDEO = "final_islamic_short.mp4"
W, H = 1080, 1920

ISLAMIC_POSTS = [
    {
        "tag": "DAILY REMINDER",
        "title": "SABR AUR TAWAKKUL",
        "quote_en": "Allah is with those who patiently persevere.",
        "quote_ur": "Beshak Allah sabr karne walon ke saath hai.",
        "ref": "Surah Al-Baqarah (2:153)",
        "accent": (52, 211, 153),
        "bg_top": (6, 46, 37),
        "bg_bot": (9, 14, 22),
        "narration": "Assalam o Alaikum. Aaj ki pyari baat: Beshak Allah sabr karne walon ke saath hai. Mushkil waqt mein sabr aur Allah par yaqeen kabhi na chhorein.",
    },
    {
        "tag": "MORNING DUA",
        "title": "RIZQ AUR BARKAT",
        "quote_en": "Seek forgiveness from your Lord; indeed, He is ever-forgiving.",
        "quote_ur": "Apne Rab se maghfirat mango, beshak woh bada bakhshne wala hai.",
        "ref": "Surah Nuh (71:10)",
        "accent": (250, 204, 21),
        "bg_top": (56, 40, 8),
        "bg_bot": (10, 13, 21),
        "narration": "Assalam o Alaikum. Astaghfar rizq aur dil ke sukoon ka zariya hai. Rozana thora waqt nikaal kar Allah se maghfirat zaroor maangein.",
    },
    {
        "tag": "HEART & SOUL",
        "title": "ZIKR SE SUKOON",
        "quote_en": "Verily, in the remembrance of Allah do hearts find rest.",
        "quote_ur": "Yaqeenan Allah ke zikr hi se dilon ko itminaan milta hai.",
        "ref": "Surah Ar-Ra'd (13:28)",
        "accent": (56, 189, 248),
        "bg_top": (10, 38, 64),
        "bg_bot": (9, 13, 22),
        "narration": "Assalam o Alaikum. Jab dil bechain ho to Allah ka zikr karein, kyunki asli sukoon sirf Allah ki yaad mein hai.",
    },
    {
        "tag": "GOOD CHARACTER",
        "title": "ACHHI BAAT",
        "quote_en": "A good word is a charity.",
        "quote_ur": "Achhi baat kehna bhi sadqa hai.",
        "ref": "Sahih Al-Bukhari",
        "accent": (167, 139, 250),
        "bg_top": (42, 22, 74),
        "bg_bot": (10, 13, 22),
        "narration": "Assalam o Alaikum. Nabi kareem sallallahu alaihi wa sallam ka farman hai ke achhi baat kehna bhi sadqa hai. Hamesha narm aur achhi baat karein.",
    },
]


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_index": -1, "last_posted": ""}


def save_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_font(size, bold=True):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def wrap_lines(draw, text, font, max_w):
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = f"{cur} {w}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def create_scene(post, date_str, out_png):
    img = Image.new("RGB", (W, H), post["bg_bot"])
    draw = ImageDraw.Draw(img)

    for y in range(0, H, 4):
        t = y / H
        r = int(post["bg_top"][0] * (1 - t) + post["bg_bot"][0] * t)
        g = int(post["bg_top"][1] * (1 - t) + post["bg_bot"][1] * t)
        b = int(post["bg_top"][2] * (1 - t) + post["bg_bot"][2] * t)
        draw.rectangle([0, y, W, y + 4], fill=(r, g, b))

    accent = post["accent"]
    f_top = load_font(34, True)
    f_pill = load_font(36, True)
    f_title = load_font(72, True)
    f_quote = load_font(48, True)
    f_sub = load_font(40, False)
    f_ref = load_font(38, True)
    f_foot = load_font(36, True)

    draw.rectangle([0, 0, W, 120], fill=(8, 12, 20))
    draw.rectangle([0, 116, W, 122], fill=accent)
    draw.text((55, 40), f"ISLAMIC REMINDER  •  {date_str.upper()}", fill=accent, font=f_top)

    draw.rounded_rectangle([55, 165, 430, 232], radius=32, fill=(18, 26, 40), outline=accent, width=3)
    draw.text((90, 177), post["tag"], fill=(255, 255, 255), font=f_pill)

    draw.text((55, 275), post["title"], fill=(255, 255, 255), font=f_title)

    draw.rounded_rectangle([55, 420, W - 55, 1540], radius=40, fill=(13, 19, 31), outline=accent, width=5)

    y_cur = 485
    for line in wrap_lines(draw, f"“{post['quote_ur']}”", f_quote, W - 210):
        draw.text((100, y_cur), line, fill=(255, 255, 255), font=f_quote)
        y_cur += 68

    y_cur += 35
    draw.line([(100, y_cur), (W - 100, y_cur)], fill=accent, width=3)
    y_cur += 40

    for line in wrap_lines(draw, post["quote_en"], f_sub, W - 210):
        draw.text((100, y_cur), line, fill=(203, 213, 225), font=f_sub)
        y_cur += 56

    draw.rounded_rectangle([100, 1365, W - 120, 1465], radius=24, fill=(22, 31, 48), outline=accent, width=3)
    draw.text((135, 1390), post["ref"], fill=accent, font=f_ref)

    draw.rectangle([0, H - 125, W, H], fill=(8, 12, 20))
    draw.text((55, H - 82), "Daily Islamic Shorts  •  Share & Subscribe", fill=(241, 245, 249), font=f_foot)

    img.save(out_png)


async def synth_edge(text, out_mp3):
    import edge_tts
    for voice in ["ur-PK-UzmaNeural", "ur-PK-AsadNeural", "hi-IN-MadhurNeural"]:
        try:
            await edge_tts.Communicate(text, voice).save(out_mp3)
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 500:
                return True
        except Exception:
            continue
    return False


def make_voice(text, out_mp3):
    ok = False
    try:
        ok = asyncio.run(synth_edge(text, out_mp3))
    except RuntimeError:
        pass
    if not ok:
        from gtts import gTTS
        gTTS(text=text, lang="hi", slow=False).save(out_mp3)


def build_video(img_p, aud_p, out_mp4):
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_p,
            "-i", aud_p,
            "-vf", f"scale={W}:{H},zoompan=z='min(zoom+0.0006,1.05)':d=300:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-shortest",
            out_mp4,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    os.makedirs(WORK_DIR, exist_ok=True)
    now = datetime.now()
    date_str = now.strftime("%d %b %Y")

    history = load_history()
    next_idx = (int(history.get("last_index", -1)) + 1) % len(ISLAMIC_POSTS)
    post = ISLAMIC_POSTS[next_idx]

    img_p = os.path.join(WORK_DIR, "islamic_scene.png")
    aud_p = os.path.join(WORK_DIR, "islamic_voice.mp3")

    create_scene(post, date_str, img_p)
    make_voice(post["narration"], aud_p)
    build_video(img_p, aud_p, FINAL_VIDEO)

    history["last_index"] = next_idx
    history["last_posted"] = now.strftime("%Y-%m-%d")
    save_history(history)
    print(f"Generated {FINAL_VIDEO} with post #{next_idx + 1}: {post['title']}")


if __name__ == "__main__":
    main()
