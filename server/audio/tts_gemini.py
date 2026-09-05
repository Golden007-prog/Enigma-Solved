"""Optional cloud TTS backend: Gemini TTS (Google GenAI), same interface as audio.tts.TTS.

Selected with TTS_BACKEND=gemini (server --tts-backend gemini). This is a deliberate,
user-requested exception to the "local at runtime" rule (docs/DECISIONS.md): use it when
the laptop cannot run Kokoro; switch back with TTS_BACKEND=kokoro. Requires GEMINI_API_KEY
(read from E:\\Enigma for Masai\\.env or server/.env — never printed).

Gemini returns 24 kHz 16-bit mono PCM with no token timestamps, so the mouth track uses the
RMS fallback (BLUEPRINT §6.3). Documented models (ai.google.dev/gemini-api/docs/speech-generation,
2026-09-05): gemini-3.1-flash-tts-preview, gemini-2.5-pro-preview-tts, gemini-2.5-flash-preview-tts.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from typing import Iterator

import numpy as np

from audio.resample import float_to_pcm16, pcm16_to_float, resample
from audio.tts import SR, TTSChunk
from audio.visemes import mouth_events_to_visemes, rms_mouth_events

log = logging.getLogger("audio.tts_gemini")

DEFAULT_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
DEFAULT_VOICE = os.environ.get("GEMINI_TTS_VOICE", "Kore")
GEMINI_SR = 24000


class GeminiTTS:
    def __init__(self, voice: str = DEFAULT_VOICE, model: str = DEFAULT_MODEL, style: str | None = None):
        from google import genai

        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set (put it in .env); cannot start the Gemini TTS backend")
        self.client = genai.Client(api_key=key)
        self.model = model
        self.voice = voice
        self.device = "gemini"
        self.style = style or "Speak as a calm, professional Indian job interviewer, clearly and at a natural pace:"
        self._use_interactions = hasattr(self.client, "interactions")
        t0 = time.perf_counter()
        # warm-up + credential check
        self._synth_pcm("Ready.", voice)
        log.info("Gemini TTS ready (%s, %s, %s API) in %.1fs", model, voice, "interactions" if self._use_interactions else "generate_content", time.perf_counter() - t0)

    # ------------------------------------------------------------------ API calls
    def _synth_pcm(self, text: str, voice: str) -> bytes:
        prompt = f"{self.style} {text}" if self.style else text
        if self._use_interactions:
            try:
                inter = self.client.interactions.create(
                    model=self.model, input=prompt, response_format={"type": "audio"},
                    generation_config={"speech_config": [{"voice": voice}]},
                )
                data = inter.output_audio.data
                return base64.b64decode(data) if isinstance(data, str) else bytes(data)
            except Exception as exc:  # noqa: BLE001 - fall back to the classic surface
                log.warning("interactions API failed (%r); falling back to generate_content", exc)
                self._use_interactions = False
        from google.genai import types

        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
            ),
        )
        part = resp.candidates[0].content.parts[0]
        data = part.inline_data.data
        return base64.b64decode(data) if isinstance(data, str) else bytes(data)

    # ------------------------------------------------------------------ TTS interface
    @staticmethod
    def split_sentences(text: str) -> list[str]:
        from audio.tts import TTS

        return TTS.split_sentences(text)

    def stream(self, text: str, voice: str | None = None, speed: float = 1.0) -> Iterator[TTSChunk]:
        voice = voice or self.voice
        offset = 0.0
        # one request per 1–2 sentences keeps time-to-first-audio low
        sentences = self.split_sentences(text)
        groups = [" ".join(sentences[i : i + 2]) for i in range(0, len(sentences), 2)] or [text]
        for group in groups:
            pcm = self._synth_pcm(group, voice)
            audio = pcm16_to_float(pcm)
            if GEMINI_SR != SR:
                audio = resample(audio, GEMINI_SR, SR)
            vis = mouth_events_to_visemes(rms_mouth_events(float_to_pcm16(audio), SR))
            for ev in vis:
                ev["t_ms"] = int(ev["t_ms"] + offset * 1000)
            dur = len(audio) / SR
            yield TTSChunk(audio=audio, pcm16=float_to_pcm16(audio), visemes=vis, start_s=offset, end_s=offset + dur, text=group, tokens=[])
            offset += dur

    def synth(self, text: str, voice: str | None = None):
        chunks = list(self.stream(text, voice))
        audio = np.concatenate([c.audio for c in chunks]) if chunks else np.zeros(0, dtype=np.float32)
        return audio, [ev for c in chunks for ev in c.visemes]
