import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Google OAuth 2.0
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "tripvideo-secret-change-me")

# Video defaults
DEFAULT_RESOLUTION = (1280, 720)
DEFAULT_PHOTO_DURATION = 4  # seconds per photo
DEFAULT_MAX_PHOTOS = 30
DEFAULT_LANG = "ko"
DEFAULT_FONT_SIZE = 24
SUBTITLE_FONT = "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"
