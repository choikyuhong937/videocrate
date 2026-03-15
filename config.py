import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Video defaults
DEFAULT_RESOLUTION = (1920, 1080)
DEFAULT_PHOTO_DURATION = 4  # seconds per photo
DEFAULT_MAX_PHOTOS = 30
DEFAULT_LANG = "ko"
DEFAULT_FONT_SIZE = 24
SUBTITLE_FONT = "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"
