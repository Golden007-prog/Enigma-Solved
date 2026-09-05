"""Delivery metrics from timestamps + audio, no LLM (BLUEPRINT §5.4).

WPM over speaking time (pauses > 0.5 s excluded), pauses > 1.0 s, latency to first word,
F0 standard deviation / range (praat-parselmouth) and RMS variance — the last two are
compared with the candidate's own Q1 baseline to raise the "monotone" flag.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger("audio.prosody")

PAUSE_EXCLUDE_S = 0.5
PAUSE_COUNT_S = 1.0
WPM_BAND = (130, 170)
HEDGE_WORDS = ("i think", "maybe", "kind of", "sort of", "probably", "i guess", "or something", "basically", "stuff")


def pitch_stats(audio: np.ndarray, sr: int) -> dict[str, float | None]:
    """F0 sd/range in Hz over voiced frames, plus RMS variance over 50 ms windows."""
    out: dict[str, float | None] = {"f0_sd_hz": None, "f0_range_hz": None, "rms_variance": None}
    x = np.asarray(audio, dtype=np.float64)
    if x.size < sr // 2:
        return out
    win = int(0.05 * sr)
    n = x.size // win
    if n > 2:
        rms = np.sqrt((x[: n * win].reshape(n, win) ** 2).mean(axis=1))
        rms = rms[rms > 0.01]  # speech-ish frames only
        if rms.size > 2:
            out["rms_variance"] = float(np.var(rms / (rms.mean() + 1e-9)))
    try:
        import parselmouth

        snd = parselmouth.Sound(x, sampling_frequency=sr)
        pitch = snd.to_pitch(time_step=0.02, pitch_floor=70.0, pitch_ceiling=400.0)
        f0 = pitch.selected_array["frequency"]
        f0 = f0[(f0 > 0) & np.isfinite(f0)]
        if f0.size > 10:
            out["f0_sd_hz"] = float(np.std(f0))
            out["f0_range_hz"] = float(np.percentile(f0, 95) - np.percentile(f0, 5))
    except Exception as exc:  # noqa: BLE001 - prosody is best-effort
        log.debug("pitch analysis unavailable: %r", exc)
    return out


def answer_delivery(answer_id: str, words: list[dict[str, Any]], duration_s: float, time_limit_s: int | None,
                    audio: np.ndarray | None = None, sr: int = 16000) -> dict[str, Any]:
    """Per-answer numbers; ``words`` are STT dicts with start/end in seconds."""
    d: dict[str, Any] = {
        "answer_id": answer_id, "duration_s": round(float(duration_s), 2), "time_limit_s": time_limit_s,
        "wpm": None, "pause_count": 0, "longest_pause_s": None, "latency_to_first_word_s": None,
    }
    if words:
        d["latency_to_first_word_s"] = round(float(words[0]["start"]), 2)
        speaking = 0.0
        pauses: list[float] = []
        prev_end = None
        for w in words:
            if prev_end is not None:
                gap = float(w["start"]) - prev_end
                if gap > PAUSE_EXCLUDE_S:
                    if gap > PAUSE_COUNT_S:
                        pauses.append(gap)
                else:
                    speaking += max(gap, 0.0)
            speaking += max(float(w["end"]) - float(w["start"]), 0.0)
            prev_end = float(w["end"])
        if speaking > 1.0:
            d["wpm"] = round(len(words) / (speaking / 60.0), 1)
        d["pause_count"] = len(pauses)
        d["longest_pause_s"] = round(max(pauses), 2) if pauses else None
    if audio is not None:
        d.update(pitch_stats(audio, sr))
    return d


def count_hedges(text: str) -> int:
    t = " " + " ".join(text.lower().split()) + " "
    return sum(t.count(" " + h + " ") for h in HEDGE_WORDS)


def aggregate(per_answer: list[dict[str, Any]], hedge_count: int, keyword_hit: list[str], keyword_missed: list[str],
              baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Session-level DeliveryMetrics (schemas.DeliveryMetrics shape)."""
    wpms = [a["wpm"] for a in per_answer if a.get("wpm")]
    lat = [a["latency_to_first_word_s"] for a in per_answer if a.get("latency_to_first_word_s") is not None]
    longest = [a["longest_pause_s"] for a in per_answer if a.get("longest_pause_s")]
    ratios = [a["duration_s"] / a["time_limit_s"] for a in per_answer if a.get("time_limit_s")]
    f0s = [a["f0_sd_hz"] for a in per_answer if a.get("f0_sd_hz")]
    rmsv = [a["rms_variance"] for a in per_answer if a.get("rms_variance") is not None]
    base = baseline or (per_answer[0] if per_answer else {})
    monotone: bool | None = None
    if f0s:
        base_sd = base.get("f0_sd_hz") or f0s[0]
        later = f0s[1:] or f0s
        monotone = bool(np.mean(later) < 0.6 * base_sd or np.mean(later) < 15.0)
    return {
        "wpm": round(float(np.mean(wpms)), 1) if wpms else None,
        "wpm_band": list(WPM_BAND),
        "pause_count": int(sum(a.get("pause_count", 0) for a in per_answer)),
        "longest_pause_s": round(max(longest), 2) if longest else None,
        "latency_to_first_word_s": round(float(np.mean(lat)), 2) if lat else None,
        "fillers_per_min": None,  # needs the optional Whisper verbatim pass
        "hedge_count": int(hedge_count),
        "time_used_ratio": round(float(np.mean(ratios)), 2) if ratios else None,
        "jd_keyword_coverage": {"hit": sorted(set(keyword_hit)), "missed": sorted(set(keyword_missed) - set(keyword_hit))},
        "f0_sd_hz": round(float(np.mean(f0s)), 1) if f0s else None,
        "rms_variance": round(float(np.mean(rmsv)), 4) if rmsv else None,
        "monotone": monotone,
        "per_answer": [
            {k: a.get(k) for k in ("answer_id", "duration_s", "time_limit_s", "wpm", "pause_count", "longest_pause_s", "latency_to_first_word_s")}
            for a in per_answer
        ],
    }
