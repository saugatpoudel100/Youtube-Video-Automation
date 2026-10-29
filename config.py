"""Central configuration. Loads secrets from a .env file (see .env.example).

Supports POOLS of keys/providers for failover:
  GROQ_API_KEYS, GEMINI_API_KEYS, ELEVENLABS_API_KEYS  -> comma-separated lists
Single-key vars (GROQ_API_KEY etc.) still work and are merged in.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _keys(*names):
    """Collect keys from one or more env vars (comma-separated), de-duped, in order."""
    out, seen = [], set()
    for n in names:
        for k in os.getenv(n, "").split(","):
            k = k.strip()
            if k and k not in seen:
                seen.add(k)
                out.append(k)
    return out


# ---- key POOLS (failover) ----
GROQ_API_KEYS = _keys("GROQ_API_KEYS", "GROQ_API_KEY")
GEMINI_API_KEYS = _keys("GEMINI_API_KEYS", "GEMINI_API_KEY")
ELEVENLABS_API_KEYS = _keys("ELEVENLABS_API_KEYS", "ELEVENLABS_API_KEY")

# which families to try first (comma list)
LLM_ORDER = [s.strip() for s in os.getenv("LLM_ORDER", "groq,gemini").split(",") if s.strip()]
TTS_ORDER = [s.strip() for s in os.getenv("TTS_ORDER", "elevenlabs,edge").split(",") if s.strip()]

# ---- single keys / models ----
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ElevenLabs
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "Roger")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
# Edge TTS (free fallback)
EDGE_VOICE = os.getenv("EDGE_VOICE", "en-US-GuyNeural")
EDGE_RATE = os.getenv("EDGE_RATE", "+8%")

# ---- behaviour ----
IG_TARGET = os.getenv("IG_TARGET", "fabrizioromano")
FB_TARGET = os.getenv("FB_TARGET", "https://www.facebook.com/fabrizioromanoherewego")
DEDUP_THRESHOLD = float(os.getenv("DEDUP_THRESHOLD", "0.8"))
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WIKI_USER_AGENT = os.getenv(
    "WIKI_USER_AGENT",
    "FootballShortsBot/1.0 (https://youtube.com/@yourchannel; you@example.com)")
YOUTUBE_CATEGORY_ID = os.getenv("YOUTUBE_CATEGORY_ID", "17")
YOUTUBE_PRIVACY = os.getenv("YOUTUBE_PRIVACY", "unlisted")
IMAGES_PER_VIDEO = int(os.getenv("IMAGES_PER_VIDEO", "5"))
MIN_LIKES = int(os.getenv("MIN_LIKES", "0"))          # 0 = no filter; e.g. 10000 for top news only
MAX_POSTS = int(os.getenv("MAX_POSTS", "0"))           # 0 = unlimited; cap new posts per scrape run
MIN_IMAGE_DIM = int(os.getenv("MIN_IMAGE_DIM", "400")) # minimum image dimension in pixels (filters icons)
MIN_IMPORTANCE = int(os.getenv("MIN_IMPORTANCE", "6")) # AI score 1-10; posts below this are skipped

# ---- paths ----
DATA_DIR = BASE_DIR / "data"
POSTS_FILE = DATA_DIR / "posts.json"
IG_IMAGES_DIR = DATA_DIR / "ig_images"
STOCK_IMAGES_DIR = DATA_DIR / "stock_images"
MY_IMAGES_DIR = DATA_DIR / "my_images"
AUDIO_DIR = DATA_DIR / "audio"
VIDEO_DIR = DATA_DIR / "video"
SESSION_DIR = BASE_DIR / "ig_session"
FB_SESSION_DIR = BASE_DIR / "fb_session"

VIDEO_W, VIDEO_H = 1080, 1920

for d in (DATA_DIR, IG_IMAGES_DIR, STOCK_IMAGES_DIR, MY_IMAGES_DIR, AUDIO_DIR, VIDEO_DIR):
    d.mkdir(parents=True, exist_ok=True)