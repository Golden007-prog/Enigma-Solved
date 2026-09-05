"""Convert the Parakeet-TDT-0.6B-v2 ONNX encoder to fp16 to halve its VRAM on the CUDA EP.

Writes models/parakeet-tdt-0.6b-v2-fp16/ (encoder fp16 + the untouched decoder/vocab/config)
and immediately checks it against the fp32 path on a fixture clip: transcript similarity and
VRAM. Run: uv run --no-sync --with onnx --with onnxconverter-common python tools/convert_parakeet_fp16.py
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import _env  # noqa: F401

import numpy as np
import soundfile as sf


def main() -> int:
    import onnx

    src_root = _env.HF_CACHE / "models--istupakov--parakeet-tdt-0.6b-v2-onnx" / "snapshots"
    snaps = sorted(src_root.glob("*"))
    if not snaps:
        print("source snapshot not found; run `hf download istupakov/parakeet-tdt-0.6b-v2-onnx` first")
        return 1
    src = snaps[-1]
    dst = _env.MODELS_DIR / "parakeet-tdt-0.6b-v2-fp16"
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("decoder_joint-model.onnx", "vocab.txt", "nemo128.onnx", "config.json"):
        shutil.copy2(src / name, dst / name)
    enc_out = dst / "encoder-model.onnx"
    if not enc_out.exists():
        t0 = time.perf_counter()
        model = onnx.load(str(src / "encoder-model.onnx"), load_external_data=True)
        # onnxruntime's converter inserts the Cast nodes that onnxconverter-common misses on this graph
        from onnxruntime.transformers.onnx_model import OnnxModel

        om = OnnxModel(model)
        om.convert_float_to_float16(keep_io_types=True)
        om.save_model_to_file(str(enc_out), use_external_data_format=True)
        for stray in dst.glob("encoder-model.onnx*.data"):
            pass
        print(f"converted encoder in {time.perf_counter() - t0:.1f}s -> {enc_out} ({(dst / 'encoder-model.onnx.data').stat().st_size / 1e9:.2f} GB)")
    else:
        print("fp16 encoder already present")

    # --- check against the fp32 path -----------------------------------------------
    _env.preload_cuda_dlls()
    import onnx_asr
    from rapidfuzz import fuzz

    wav = _env.FIXTURES_DIR / "sample_answer_strong_16k.wav"
    audio, sr = sf.read(wav, dtype="float32")
    script = (_env.FIXTURES_DIR / "sample_answer_strong.txt").read_text(encoding="utf-8")
    results = {}
    for label, kwargs in (("fp16", {"path": str(dst)}), ("fp32", {})):
        m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v2", providers=["CUDAExecutionProvider", "CPUExecutionProvider"], **kwargs).with_timestamps()
        m.recognize(audio[: sr * 2], sample_rate=sr)
        t0 = time.perf_counter()
        r = m.recognize(audio, sample_rate=sr)
        dt = time.perf_counter() - t0
        mem = _env.gpu_mem_mib()
        sim = fuzz.ratio(r.text.lower(), script.lower())
        results[label] = (sim, dt, mem[0] if mem else None)
        print(f"[{label}] sim={sim:.1f} latency={dt * 1000:.0f}ms VRAM={mem[0] if mem else '?'} MiB text={r.text[:90]!r}")
        del m
    ok = results["fp16"][0] >= 95 and abs(results["fp16"][0] - results["fp32"][0]) < 3
    print("RESULT:", "PASS (use fp16 dir)" if ok else "FAIL (keep fp32)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
