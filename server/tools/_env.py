"""Shared environment setup for the probe/tool scripts.

Import this first in every tool. It pins the Hugging Face cache to
server/models/hf-cache so every weight lives inside the repo's model dir,
and it makes espeak-ng discoverable for Kokoro/misaki on Windows.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = Path(os.environ.get("MODELS_DIR", SERVER_DIR / "models"))
HF_CACHE = MODELS_DIR / "hf-cache"
FIXTURES_DIR = SERVER_DIR / "fixtures"
DATA_DIR = SERVER_DIR / "data"

os.environ.setdefault("HF_HUB_CACHE", str(HF_CACHE))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# espeak-ng on Windows: misaki/phonemizer look at these when the bundled
# espeakng-loader wheel is unavailable. Harmless if espeak is not needed.
_ESPEAK_DIR = Path(r"C:\Program Files\eSpeak NG")
if _ESPEAK_DIR.exists():
    os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", str(_ESPEAK_DIR / "libespeak-ng.dll"))
    os.environ.setdefault("PHONEMIZER_ESPEAK_PATH", str(_ESPEAK_DIR / "espeak-ng.exe"))
    os.environ.setdefault("ESPEAK_DATA_PATH", str(_ESPEAK_DIR / "espeak-ng-data"))

# Make `server/` importable (audio/, brain/, store/) when a tool is run directly.
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


def preload_cuda_dlls() -> str:
    """Load CUDA/cuDNN DLLs for onnxruntime-gpu from the nvidia-* wheels or torch.

    Returns a short status string for logging. onnxruntime >= 1.21 exposes
    preload_dlls(); older builds find the DLLs via PATH, so we also add the
    nvidia wheel bin dirs to PATH as a fallback.
    """
    notes = []
    try:
        import onnxruntime as ort  # noqa: WPS433

        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
            notes.append("ort.preload_dlls()")
    except Exception as exc:  # pragma: no cover - diagnostic only
        notes.append(f"preload_dlls failed: {exc!r}")
    try:
        import nvidia  # type: ignore  # noqa: WPS433

        for p in nvidia.__path__:
            for sub in Path(p).glob("*/bin"):
                os.environ["PATH"] = str(sub) + os.pathsep + os.environ["PATH"]
                if hasattr(os, "add_dll_directory"):
                    os.add_dll_directory(str(sub))
        notes.append("nvidia wheel bin dirs on PATH")
    except Exception:
        pass
    try:
        import torch  # noqa: WPS433

        lib = Path(torch.__file__).parent / "lib"
        if lib.exists():
            os.environ["PATH"] = str(lib) + os.pathsep + os.environ["PATH"]
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(lib))
            notes.append("torch/lib on PATH")
    except Exception:
        pass
    return "; ".join(notes)


def gpu_mem_mib() -> tuple[int, int] | None:
    """(used, total) dedicated VRAM in MiB via nvidia-smi, or None."""
    import subprocess

    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip().splitlines()[0]
        used, total = (int(x.strip()) for x in out.split(","))
        return used, total
    except Exception:
        return None
