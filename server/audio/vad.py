"""Turn detection on the incoming 16 kHz PCM16 stream: Silero VAD (ONNX, CPU) + a silence timer.

Feed 20 ms client frames; the detector re-chunks into Silero's 512-sample windows, emits
``speech_start`` / ``speech_end`` events, and hands back the turn's audio on ``speech_end``.
The 700 ms end-of-turn rule (v1) is ``silence_ms``; Smart Turn can replace ``_ended`` later.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np

SR = 16000
WINDOW = 512  # samples per Silero window at 16 kHz (32 ms)


@dataclass
class VadEvent:
    kind: str                # "speech_start" | "speech_end"
    t_s: float               # stream time in seconds
    audio: np.ndarray | None = None   # turn audio (float32) on speech_end
    speech_s: float = 0.0    # accumulated speech length in this turn


class TurnDetector:
    def __init__(self, silence_ms: int = 700, threshold: float = 0.5, min_speech_ms: int = 250, pre_roll_ms: int = 300,
                 max_turn_s: float = 120.0):
        from silero_vad import load_silero_vad

        self.model = load_silero_vad(onnx=True)
        self.threshold = threshold
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.max_turn_s = max_turn_s
        self.pre_roll = int(pre_roll_ms / 1000 * SR)
        self.reset()

    def reset(self) -> None:
        self.model.reset_states()
        self._pending = np.zeros(0, dtype=np.float32)
        self._ring = np.zeros(0, dtype=np.float32)   # pre-roll kept before speech starts
        self._turn: list[np.ndarray] = []
        self.in_speech = False
        self.stream_t = 0.0
        self.speech_t = 0.0
        self._silence_t = 0.0
        self._last_speech_t = 0.0

    def feed_pcm16(self, frame: bytes) -> list[VadEvent]:
        x = np.frombuffer(frame, dtype="<i2").astype(np.float32) / 32768.0
        return self.feed(x)

    def feed(self, x: np.ndarray) -> list[VadEvent]:
        import torch

        events: list[VadEvent] = []
        self._pending = np.concatenate([self._pending, x])
        while len(self._pending) >= WINDOW:
            win, self._pending = self._pending[:WINDOW], self._pending[WINDOW:]
            prob = float(self.model(torch.from_numpy(win), SR).item())
            self.stream_t += WINDOW / SR
            voiced = prob >= self.threshold
            if not self.in_speech:
                self._ring = np.concatenate([self._ring, win])[-self.pre_roll:]
                if voiced:
                    self.in_speech = True
                    self.speech_t = WINDOW / SR
                    self._silence_t = 0.0
                    self._turn = [self._ring.copy(), win]
                    self._last_speech_t = self.stream_t
                    events.append(VadEvent("speech_start", self.stream_t))
                continue
            self._turn.append(win)
            if voiced:
                self.speech_t += WINDOW / SR
                self._silence_t = 0.0
                self._last_speech_t = self.stream_t
            else:
                self._silence_t += WINDOW / SR
            turn_len = sum(len(a) for a in self._turn) / SR
            if self._silence_t * 1000 >= self.silence_ms or turn_len >= self.max_turn_s:
                audio = np.concatenate(self._turn)
                # trim the trailing silence beyond 200 ms so the clip ends cleanly
                keep = int(len(audio) - max(0.0, self._silence_t - 0.2) * SR)
                audio = audio[: max(keep, 0)]
                kind = "speech_end" if self.speech_t * 1000 >= self.min_speech_ms else "speech_discard"
                events.append(VadEvent(kind, self.stream_t, audio if kind == "speech_end" else None, self.speech_t))
                self.in_speech = False
                self._turn = []
                self._ring = np.zeros(0, dtype=np.float32)
                self.speech_t = 0.0
                self._silence_t = 0.0
                self.model.reset_states()
        return events

    def force_end(self) -> VadEvent | None:
        """Push-to-talk release or time-out: close the open turn now."""
        if not self.in_speech or not self._turn:
            return None
        audio = np.concatenate(self._turn)
        ev = VadEvent("speech_end", self.stream_t, audio, self.speech_t)
        self.in_speech = False
        self._turn = []
        self.model.reset_states()
        return ev


class BargeInDetector:
    """While TTS plays, count voiced audio; fire once ``min_speech_ms`` of speech is heard."""

    def __init__(self, min_speech_ms: int = 350, threshold: float = 0.5):
        from silero_vad import load_silero_vad

        self.model = load_silero_vad(onnx=True)
        self.min_speech_ms = min_speech_ms
        self.threshold = threshold
        self.reset()

    def reset(self) -> None:
        self.model.reset_states()
        self._pending = np.zeros(0, dtype=np.float32)
        self.speech_ms = 0.0
        self.fired = False

    def feed_pcm16(self, frame: bytes) -> bool:
        import torch

        x = np.frombuffer(frame, dtype="<i2").astype(np.float32) / 32768.0
        self._pending = np.concatenate([self._pending, x])
        while len(self._pending) >= WINDOW:
            win, self._pending = self._pending[:WINDOW], self._pending[WINDOW:]
            prob = float(self.model(torch.from_numpy(win), SR).item())
            self.speech_ms = self.speech_ms + WINDOW / SR * 1000 if prob >= self.threshold else max(0.0, self.speech_ms - 16)
            if self.speech_ms >= self.min_speech_ms and not self.fired:
                self.fired = True
                return True
        return False


def now_ms() -> int:
    return int(time.monotonic() * 1000)
