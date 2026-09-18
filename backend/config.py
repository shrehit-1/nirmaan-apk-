"""
NIRMAAN - Configuration Settings
"""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")

# Load environment variables from root .env if present
load_dotenv(os.path.join(ROOT_DIR, ".env"))

HOST = "0.0.0.0"
PORT = 8000
APP_NAME = "NIRMAAN"
APP_VERSION = "1.0.0"

# AI Image Generation API Configuration
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip())
# NOTE: override either of these in .env if your account has access to a
# different/newer Gemini model name than what's hardcoded below.
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image").strip()
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash").strip()

# Sarvam AI Configuration (Saaras v3 speech-to-text, Bulbul v3 text-to-speech)
# Get a free key at https://dashboard.sarvam.ai/ and put it in .env as
# SARVAM_API_KEY=... — genuine Indian-language speech models, purpose-built
# for regional accents and code-mixing, as opposed to Gemini's general
# audio understanding (used as the fallback if this isn't configured).
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "").strip()
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3").strip()
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3").strip()

