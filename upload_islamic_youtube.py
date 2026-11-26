import argparse
import json
import os
import sys
from datetime import datetime

SHORT_VIDEO_FILE = "final_islamic_short.mp4"
LONG_VIDEO_FILE = "final_islamic_long.mp4"
LONG_META_FILE = "long_meta.json"
LONG_THUMBNAIL_FILE = "long_thumbnail.jpg"


def parse_args():
    parser = argparse.ArgumentParser(description="Prepare Islamic video without auto-uploading to YouTube.")
    parser.add_argument("--long", action="store_true", help="Use generated long-form Islamic video metadata")
    return parser.parse_args()


def main():
    args = parse_args()
    today_str = datetime.now().strftime("%d %b %Y")

    if args.long:
        video_file = LONG_VIDEO_FILE
        meta_data = {}
        if os.path.exists(LONG_META_FILE):
            try:
                with open(LONG_META_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        meta_data = loaded
            except Exception as e:
                print(f"Warning: could not read {LONG_META_FILE}: {e}")

        video_file = str(meta_data.get("video_path") or video_file)
        if not os.path.exists(video_file):
            print(f"Error: {video_file} not found.")
            sys.exit(1)

        title = str(meta_data.get("title") or f"Complete Islamic Story ({today_str}) | Urdu Waqia")[:100].strip()
        description = str(
            meta_data.get("description")
            or (
                f"Complete Islamic Story in Urdu ({today_str}).\n"
                "Listen, reflect, and share.\n\n"
                "#Storybox #IslamicStory #UrduWaqiat #IslamicReminder"
            )
        )
        raw_tags = meta_data.get("tags")
        if isinstance(raw_tags, list) and raw_tags:
            tags = [str(t).strip() for t in raw_tags if str(t).strip()][:25]
        else:
            tags = ["islamic story urdu", "urdu waqiat", "islamic reminder", "storybox"]

        thumb_path = str(meta_data.get("thumbnail_path") or LONG_THUMBNAIL_FILE)
    else:
        video_file = SHORT_VIDEO_FILE
        if not os.path.exists(video_file):
            print(f"Error: {video_file} not found.")
            sys.exit(1)

        title = f"Daily Islamic Reminder ({today_str}) | Urdu Quote & Dua #Shorts"[:100]
        description = (
            f"Daily Islamic Reminder & Heart-Touching Quote ({today_str}).\n"
            "Listen, reflect, and share peace and positivity.\n"
            "Subscribe for daily Islamic Shorts.\n\n"
            "#IslamicShorts #IslamicReminder #UrduQuotes #DailyDua #SubhanAllah #Shorts"
        )
        tags = [
            "islamic shorts",
            "islamic reminder",
            "urdu islamic quotes",
            "daily dua",
            "islamic status",
            "shorts",
        ]
        thumb_path = ""

    print("Auto-upload is disabled. Video was not uploaded to YouTube.")
    print(f"File: {video_file}")
    print(f"Title: {title}")
    if args.long and thumb_path:
        print(f"Thumbnail path: {thumb_path}")


if __name__ == "__main__":
    main()
