@echo off
REM Interview Cracker — one double-click from cold to READY (BLUEPRINT §8.3, master prompt Phase 7).
REM Prereqs done once with internet: models downloaded (Phase 1), `uv sync`, LM Studio installed.
setlocal
cd /d "%~dp0"
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set PYTHONIOENCODING=utf-8
if "%SUPABASE_MODE%"=="" set SUPABASE_MODE=off

echo [1/5] LM Studio daemon
call lms daemon up
echo [2/5] LM Studio server on 127.0.0.1:1234 (never bound to the LAN)
call lms server start --port 1234 --bind 127.0.0.1
echo [3/5] Loading qwen/qwen3.5-9b (Q6_K, 8K ctx, 1 slot) as "interviewer"
call lms ps | findstr /i "interviewer" >nul || call lms load qwen/qwen3.5-9b -y --gpu max --context-length 8192 --parallel 1 --identifier interviewer
echo [4/5] Self-test (STT + TTS + LLM, prints tok/s and VRAM)
uv run --no-sync python tools\selftest.py
if errorlevel 1 (
  echo.
  echo SELFTEST FAILED — fix the line above before the demo.
  pause
  exit /b 1
)
echo [5/5] Voice server on 0.0.0.0:8765  (pair page opens in the browser)
start "" http://localhost:8765/pair
uv run --no-sync python server.py --host 0.0.0.0 --port 8765 --emulator %*
pause
