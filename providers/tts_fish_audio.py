"""Fish Audio speech synthesis, adapted to the pipeline's PCM TTS contract."""
from __future__ import annotations

import asyncio
import io
import json
import struct
import wave
from importlib.util import find_spec
from typing import AsyncIterator

from . import audio
from .base import DEFAULT_CAPS, Field

API = "https://api.fish.audio/v1/tts"

MODELS = (
    "s1",
    "s2-pro",
    "s2.1-pro",
    "s2.1-pro-free",
    "drama-3",
    "s3-pro",
)
DEFAULT_MODEL = "s2.1-pro-free"
LATENCIES = ("low", "normal", "balanced")
DEFAULT_LATENCY = "balanced"


class FishAudioTTS:
    def __init__(self, cfg: dict):
        self.key = str(cfg.get("api_key") or "").strip()
        self.reference_id = str(cfg.get("reference_id") or "").strip()
        self.model = str(cfg.get("model") or "").strip() or DEFAULT_MODEL
        self.latency = str(cfg.get("latency") or "").strip() or DEFAULT_LATENCY
        if self.model not in MODELS:
            raise RuntimeError("Unsupported Fish Audio model selected.")
        if self.latency not in LATENCIES:
            raise RuntimeError("Unsupported Fish Audio latency selected.")
        self.caps = dict(DEFAULT_CAPS)
        self.caps["audio_out"] = True

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "model": self.model,
        }

    def _payload(self, text: str, reference_id: str) -> dict:
        return {
            "text": text,
            "reference_id": reference_id,
            "format": "wav",
            "sample_rate": audio.SPEAKER_RATE,
            "latency": self.latency,
        }

    async def speak(self, text: str, voice: str = "") -> AsyncIterator[bytes]:
        import httpx

        reference_id = str(voice or "").strip() or self.reference_id
        if not self.key:
            raise RuntimeError("No Fish Audio API key is set.")
        if not reference_id:
            raise RuntimeError("No Fish Audio reference ID is set.")
        text = (text or "").strip()
        if not text:
            return

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    API,
                    headers=self._headers(),
                    json=self._payload(text, reference_id),
                )
        except httpx.TimeoutException:
            raise RuntimeError("Fish Audio request timed out.") from None
        except httpx.RequestError as exc:
            detail = str(exc).replace(self.key, "[redacted]")[:160]
            raise RuntimeError(f"Fish Audio connection failed: {detail}") from None

        if response.status_code >= 400:
            message = _error_message(response.text, self.key)
            raise RuntimeError(
                f"Fish Audio request failed with HTTP {response.status_code}: "
                f"{message}"
            )

        pcm = await asyncio.to_thread(_wav_to_pcm, response.content)
        for piece in audio.chunk(pcm):
            yield piece

    def models(self) -> list[str]:
        """Model IDs accepted by the official TTS endpoint."""
        return list(MODELS)

    def probe(self) -> tuple[bool, str]:
        if not self.key:
            return False, "No API key set."
        if not self.reference_id:
            return False, "No reference ID set."
        return True, (
            f"Configuration ready for {self.model} ({self.latency} latency). "
            "API access is checked during synthesis."
        )


def _error_message(body: str, api_key: str) -> str:
    safe_body = (body or "").replace(api_key, "[redacted]") if api_key else body
    try:
        payload = json.loads(safe_body)
        if isinstance(payload, dict):
            value = payload.get("message") or payload.get("detail") \
                or payload.get("reason") or payload
        else:
            value = payload
        return " ".join(str(value).split())[:160]
    except (TypeError, ValueError):
        return " ".join((safe_body or "").split())[:160] or "Unknown error"


def _wav_to_pcm(data: bytes) -> bytes:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RuntimeError("Fish Audio returned an invalid WAV response.")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            frames = wav.getnframes()
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            if (frames <= 0 or channels <= 0 or width not in (1, 2, 3, 4)
                    or wav.getframerate() <= 0):
                raise ValueError("empty WAV")
            if len(wav.readframes(frames)) != frames * channels * width:
                raise ValueError("truncated WAV")
        pcm = audio.wav_to_pcm(data, want_rate=audio.SPEAKER_RATE)
    except (EOFError, OSError, ValueError, wave.Error, struct.error):
        raise RuntimeError("Fish Audio returned an invalid WAV response.") from None
    if not pcm:
        raise RuntimeError("Fish Audio returned empty audio.")
    return pcm


def _make(cfg: dict) -> FishAudioTTS:
    return FishAudioTTS(cfg)


PROVIDER = {
    "id": "fish_audio",
    "kind": "tts",
    "label": "Fish Audio",
    "hint": "Cloud voice synthesis using a Fish Audio reference ID",
    "requires": ("httpx",),
    "needs": (
        Field("api_key", "API key", kind="secret",
              hint="Fish Audio account API key"),
        Field("reference_id", "Reference ID", required=True,
              hint="Voice model ID from your Fish Audio account"),
        Field("model", "Fish Audio model", kind="choice", choices=MODELS,
              default=DEFAULT_MODEL, required=False),
        Field("latency", "Latency", kind="choice", choices=LATENCIES,
              default=DEFAULT_LATENCY, required=False, advanced=True),
    ),
    "caps": {"audio_out": True},
    "factory": _make,
}


def available() -> bool:
    return find_spec("httpx") is not None
