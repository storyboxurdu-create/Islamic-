import os
import sys
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

VIDEO_FILE = "final_islamic_short.mp4"


def get_youtube_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def main():
    if not os.path.exists(VIDEO_FILE):
        print(f"Error: {VIDEO_FILE} not found.")
        sys.exit(1)

    today_str = datetime.now().strftime("%d %b %Y")
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

    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(VIDEO_FILE, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()

    print("Uploaded successfully! Video ID:", response.get("id"))


if __name__ == "__main__":
    main()
