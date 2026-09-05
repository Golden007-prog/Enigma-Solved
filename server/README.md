# Interview Cracker — voice server

Python 3.12 + `uv`. One process holds every GPU speech model (Parakeet STT, Kokoro TTS); Silero VAD runs on CPU; the LLM is served by LM Studio on `127.0.0.1:1234`.

```powershell
cd "E:\Enigma for Masai\server"
uv sync
$env:HF_HUB_OFFLINE=1
uv run python tools/selftest.py
uv run python server.py --host 0.0.0.0 --port 8765 --emulator
```

Layout, protocol and brain stages: see `../docs/BLUEPRINT.md` §4–§8 and `../CLAUDE.md`.
Secrets live in `.env` (copy `env.example` to `.env`); never commit it.
