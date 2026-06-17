"""Central config — all tunable parameters."""
import os

W, H   = 1920, 1080
FPS    = 24
ASPECT = "16:9"

FONTS = {
    "ta_black"  : "/usr/share/fonts/truetype/noto/NotoSansTamil-Black.ttf",
    "ta_bold"   : "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf",
    "ta_regular": "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf",
    "en_black"  : "/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
    "en_bold"   : "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "en_regular": "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
}

BASE_DIR    = "/tmp/documentary"
ASSET_DIR   = f"{BASE_DIR}/assets"
FRAME_DIR   = f"{BASE_DIR}/frames"
AUDIO_DIR   = f"{BASE_DIR}/audio"
VIDEO_DIR   = f"{BASE_DIR}/video"
CACHE_DIR   = f"{BASE_DIR}/cache"
SCRIPT_DIR  = f"{BASE_DIR}/scripts"

PEXELS_KEY  = os.environ.get("PEXELS_API_KEY","")
GEMINI_KEY  = os.environ.get("GEMINI_KEY","")

# Pattern interrupt: max seconds before a visual change MUST occur
MAX_STATIC_SECONDS = 3.0

# Caption: max words per line
CAPTION_MAX_WORDS = 4

# Motion: default Ken Burns zoom range
KB_ZOOM_MIN = 1.0
KB_ZOOM_MAX = 1.12
