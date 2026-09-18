"""
NIRMAAN - Sarvam AI Service
Genuine integration with Sarvam AI's Saaras v3 (speech-to-text) and Bulbul
v3 (text-to-speech) models — purpose-built for Indian languages, regional
accents, and code-mixed speech, exactly as described in the pitch deck.

This calls Sarvam's REST API directly over HTTPS (no extra SDK dependency
needed beyond httpx, which the project already uses).

Docs: https://docs.sarvam.ai
"""
import os
import base64
from typing import Optional, Dict, Any

import httpx

from ..config import SARVAM_API_KEY, SARVAM_STT_MODEL, SARVAM_TTS_MODEL

SARVAM_BASE_URL = "https://api.sarvam.ai"

# Sarvam's BCP-47 language codes (10 Indic languages + English)
SARVAM_LANGUAGE_CODES = {
    "hi": "hi-IN", "bn": "bn-IN", "ta": "ta-IN", "te": "te-IN",
    "gu": "gu-IN", "kn": "kn-IN", "ml": "ml-IN", "mr": "mr-IN",
    "pa": "pa-IN", "od": "od-IN", "en": "en-IN",
}


class SarvamService:
    def __init__(self):
        self.last_error: Optional[str] = None

    def _get_api_key(self) -> str:
        return (os.getenv("SARVAM_API_KEY", "").strip() or SARVAM_API_KEY).strip()

    def is_available(self) -> bool:
        key = self._get_api_key()
        return bool(key and len(key) > 5)

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> Optional[Dict[str, Any]]:
        """
        Sends audio to Sarvam's Saaras v3 speech-to-text model. Expects
        WAV audio (already transcoded upstream) under 30 seconds — Saaras
        v3's synchronous REST limit.

        Returns {"transcript_original": str, "detected_language": "hi"|"en"|...,
                 "language_name": str} on success, or None on failure
        (self.last_error is set with the reason).
        """
        self.last_error = None
        api_key = self._get_api_key()
        if not api_key:
            self.last_error = "SARVAM_API_KEY is not configured on the server."
            return None
        if not audio_bytes:
            self.last_error = "No audio data was received."
            return None

        try:
            model = os.getenv("SARVAM_STT_MODEL", SARVAM_STT_MODEL or "saaras:v3").strip()
            resp = httpx.post(
                f"{SARVAM_BASE_URL}/speech-to-text",
                headers={"api-subscription-key": api_key},
                files={"file": (filename, audio_bytes, "audio/wav")},
                data={"model": model, "mode": "transcribe"},
                timeout=30.0,
            )
            if resp.status_code != 200:
                self.last_error = f"Sarvam STT HTTP {resp.status_code}: {resp.text[:300]}"
                return None

            data = resp.json()
            transcript = (data.get("transcript") or "").strip()
            sarvam_lang = (data.get("language_code") or "").strip()  # e.g. "hi-IN"
            lang_code = sarvam_lang.split("-")[0].lower() if sarvam_lang else "en"

            from .speech_service import LANGUAGES
            language_name = LANGUAGES.get(lang_code, LANGUAGES["en"])

            return {
                "transcript_original": transcript,
                "detected_language": lang_code,
                "language_name": language_name,
            }
        except httpx.TimeoutException:
            self.last_error = "Sarvam STT request timed out."
            return None
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            print(f"[SarvamService] Transcription failed: {self.last_error}")
            return None

    def synthesize(self, text: str, language_code: str = "hi-IN", speaker: str = "anushka") -> Optional[bytes]:
        """
        Sends text to Sarvam's Bulbul v3 text-to-speech model. Returns raw
        WAV audio bytes on success, or None on failure.
        """
        self.last_error = None
        api_key = self._get_api_key()
        if not api_key:
            self.last_error = "SARVAM_API_KEY is not configured on the server."
            return None
        if not text or not text.strip():
            self.last_error = "No text provided to synthesize."
            return None

        # Bulbul v3 accepts up to 2500 characters per request
        text = text.strip()[:2500]

        try:
            model = os.getenv("SARVAM_TTS_MODEL", SARVAM_TTS_MODEL or "bulbul:v3").strip()
            resp = httpx.post(
                f"{SARVAM_BASE_URL}/text-to-speech",
                headers={
                    "api-subscription-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "language_code": language_code,
                    "model": model,
                    "speaker": speaker,
                },
                timeout=30.0,
            )
            if resp.status_code != 200:
                self.last_error = f"Sarvam TTS HTTP {resp.status_code}: {resp.text[:300]}"
                return None

            data = resp.json()
            audios = data.get("audios") or []
            if not audios:
                self.last_error = "Sarvam TTS returned no audio."
                return None

            combined_b64 = "".join(audios)
            return base64.b64decode(combined_b64)
        except httpx.TimeoutException:
            self.last_error = "Sarvam TTS request timed out."
            return None
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            print(f"[SarvamService] Synthesis failed: {self.last_error}")
            return None


sarvam_service = SarvamService()
