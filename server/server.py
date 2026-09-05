"""Interview Cracker voice server (BLUEPRINT §4.1 / §4.2 / §8).

One process holds every GPU speech model; the LLM is LM Studio on 127.0.0.1:1234.
    uv run python server.py --host 0.0.0.0 --port 8765 [--emulator] [--stt cuda|cpu]

HTTP:  GET /health · GET /pair (QR) · GET /pair.json · GET /report/{session} · GET /report/{session}/view
       GET /clips/{session}/{idx}.wav · GET /sessions · /static/test.html
WS:    /ws — JSON control frames + binary PCM16 (640-byte / 20 ms @ 16 kHz in, 24 kHz out)
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import logging
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from tools import _env  # noqa: E402  (HF cache, espeak, model dirs)

try:  # secrets live in server/.env (never committed); missing file is fine
    from dotenv import load_dotenv

    load_dotenv(SERVER_DIR.parent / ".env")   # repo-root .env (e.g. GEMINI_API_KEY)
    load_dotenv(SERVER_DIR / ".env")          # server/.env (Supabase keys etc.)
except Exception:  # noqa: BLE001
    pass

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import protocol as P  # noqa: E402
from audio.prosody import aggregate, answer_delivery, count_hedges  # noqa: E402
from audio.resample import to_16k_pcm16  # noqa: E402
from brain import prompts  # noqa: E402
from brain.interview import InterviewBrain, Turn  # noqa: E402
from brain.llm import LLM  # noqa: E402
from store.db import DB  # noqa: E402
from store.sync import SupabaseSync  # noqa: E402

VERSION = "0.1.0"
log = logging.getLogger("server")

ECHO_GATE_S = 0.6          # ignore VAD for this long after the interviewer stops (§ Phase 2.2)
BARGE_IN_MS = 350          # Tough only: speech this long during TTS → interrupt
NOD_EVERY_S = (6.0, 9.0)   # Warm-up/Realistic: nod while the candidate speaks
DEFAULT_PORT = 8765


# ---------------------------------------------------------------------------
# Models (loaded once)
# ---------------------------------------------------------------------------


class Models:
    def __init__(self) -> None:
        self.stt = None
        self.tts = None
        self.llm: LLM | None = None
        self.turn_detector_factory = None
        self.info: dict[str, Any] = {}

    def load(self, args: argparse.Namespace) -> None:
        from audio.stt import STT
        from audio.tts import TTS
        from audio.vad import TurnDetector  # noqa: F401  (import check)

        t0 = time.perf_counter()
        self.llm = LLM(model=args.llm_model)
        ok, msg = self.llm.health()
        self.info["llm"] = msg
        if not ok:
            log.warning("LLM: %s", msg)
        self.stt = STT(prefer_cuda=(args.stt == "cuda"))
        self.info["stt"] = self.stt.provider
        if args.tts_backend == "gemini":
            from audio.tts_gemini import GeminiTTS

            self.tts = GeminiTTS(voice=args.gemini_voice)
            self.info["tts"] = f"gemini/{self.tts.model}/{self.tts.voice}"
            log.warning("TTS backend is Gemini (cloud) — not local; switch back with --tts-backend kokoro / TTS_BACKEND=kokoro")
        else:
            self.tts = TTS(voice=args.voice, device=args.tts_device)
            self.info["tts"] = f"kokoro/{self.tts.device}/{self.tts.voice}"
        mem = _env.gpu_mem_mib()
        self.info["vram_mib"] = mem[0] if mem else None
        self.info["load_s"] = round(time.perf_counter() - t0, 1)
        log.info("models ready in %.1fs: %s", time.perf_counter() - t0, self.info)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class Session:
    def __init__(self, ws: WebSocket, app: "App"):
        self.ws = ws
        self.app = app
        self.models = app.models
        self.db = app.db
        self.state = P.SessionState.PAIR
        self.pressure = P.Pressure.REALISTIC
        self.sid: str | None = None
        self.brain: InterviewBrain | None = None
        self.hello: P.HelloMessage | None = None
        self.send_lock = asyncio.Lock()
        self.closed = False
        # audio
        from audio.vad import BargeInDetector, TurnDetector

        self.detector = TurnDetector(silence_ms=700)
        self.barge = BargeInDetector(min_speech_ms=BARGE_IN_MS)
        self.echo_gate_until = 0.0
        self.tts_task: asyncio.Task | None = None
        self.tts_cancel = threading.Event()
        self.tts_started_at = 0.0
        self.tts_audio_s = 0.0
        self.ptt_down = False
        self.timer_task: asyncio.Task | None = None
        self.nod_task: asyncio.Task | None = None
        self.turn_started_at = 0.0
        # bookkeeping
        self.turn: Turn | None = None
        self.turn_db_ids: dict[int, str] = {}
        self.per_answer: list[dict[str, Any]] = []
        self.hedges = 0
        self.kw_hit: list[str] = []
        self.kw_missed: list[str] = []
        self.latencies: list[float] = []
        self.answer_end_wall = 0.0
        self.provisional: tuple[dict, dict] | None = None

    # ------------------------------------------------------------------ io
    async def send(self, msg: Any) -> None:
        if self.closed:
            return
        text = P.encode_server_message(msg)
        async with self.send_lock:
            await self.ws.send_text(text)

    async def send_bytes(self, data: bytes) -> None:
        if self.closed:
            return
        async with self.send_lock:
            await self.ws.send_bytes(data)

    async def error(self, code: P.ErrorCode, message: str, fatal: bool = False) -> None:
        await self.send(P.ErrorMessage(code=code, message=message, fatal=fatal))
        if fatal:
            self.closed = True
            try:
                await self.ws.close()
            except Exception:  # noqa: BLE001
                pass

    def set_state(self, target: P.SessionState) -> None:
        if self.state is target:
            return
        if not P.can_transition(self.state, target, pressure=self.pressure):
            log.debug("fsm: forcing %s -> %s", self.state, target)
        self.state = target

    # ------------------------------------------------------------------ main loop
    async def run(self) -> None:
        try:
            while not self.closed:
                msg = await self.ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    await self.on_audio(msg["bytes"])
                elif msg.get("text") is not None:
                    await self.on_text(msg["text"])
        except WebSocketDisconnect:
            pass
        finally:
            self.closed = True
            self.tts_cancel.set()
            for t in (self.tts_task, self.timer_task, self.nod_task):
                if t:
                    t.cancel()
            if self.sid and self.state not in (P.SessionState.REPORT,):
                self.db.end_session(self.sid, "aborted")
            self.app.sessions.pop(id(self), None)
            log.info("session %s closed in state %s", self.sid, self.state)

    async def on_text(self, text: str) -> None:
        try:
            m = P.parse_client_message(text)
        except P.ProtocolError as e:
            await self.error(e.code, e.message)
            return
        if isinstance(m, P.HelloMessage):
            await self.on_hello(m)
        elif isinstance(m, P.PingMessage):
            await self.send(P.PongMessage(t=m.t))
        elif isinstance(m, P.PttMessage):
            self.ptt_down = m.state == "down"
            if m.state == "up" and self.state is P.SessionState.LISTENING:
                ev = self.detector.force_end()
                if ev and ev.audio is not None:
                    await self.send(P.VadMessage(state="speech_end"))
                    asyncio.create_task(self.on_answer(ev.audio))
        elif isinstance(m, P.CancelMessage):
            if self.state in P.ROUND_STATES:
                await self.finish_round(reason="cancelled")
            else:
                await self.error(P.ErrorCode.BAD_STATE, f"nothing to cancel in {self.state}")

    async def on_hello(self, m: P.HelloMessage) -> None:
        if m.token != self.app.token:
            await self.error(P.ErrorCode.BAD_TOKEN, "token does not match this server's pairing token", fatal=True)
            return
        if self.sid:
            await self.error(P.ErrorCode.BAD_STATE, "already paired")
            return
        if not m.jd or not m.jd.strip():
            await self.error(P.ErrorCode.BAD_MESSAGE, "hello.jd is required (paste the job description first)", fatal=True)
            return
        self.hello = m
        self.pressure = m.pressure
        self.sid = self.db.create_session(m.jd, m.pressure.value, m.voice, device_id=self.app.sync.device_id,
                                          device_info={"client": "ws", "in": m.audio_in.model_dump(), "out": m.audio_out.model_dump()}, server_version=VERSION)
        self.app.sessions[id(self)] = self
        await self.send(P.ReadyMessage(session=self.sid))
        asyncio.create_task(self.start_round())

    # ------------------------------------------------------------------ round
    async def start_round(self) -> None:
        try:
            await self._start_round()
        except Exception as exc:  # noqa: BLE001
            log.exception("start_round failed")
            await self.error(P.ErrorCode.INTERNAL, f"start failed: {exc!s}"[:300], fatal=True)

    async def _start_round(self) -> None:
        assert self.hello and self.sid and self.models.llm
        self.set_state(P.SessionState.PREP)
        t0 = time.perf_counter()
        try:
            self.brain = InterviewBrain(self.models.llm, self.hello.jd or "", self.pressure.value, self.sid)
            rubric = await self.brain.build_rubric()
        except Exception as exc:  # noqa: BLE001
            log.exception("Stage A failed")
            await self.error(P.ErrorCode.INTERNAL, f"Stage A failed: {exc!s}"[:300], fatal=True)
            return
        log.info("%s Stage A: %d competencies (rejected %s, reasked=%s) in %.1fs", self.sid, len(rubric["competencies"]), self.brain.rejected_ids, self.brain.reasked, time.perf_counter() - t0)
        self.db.set_rubric(self.sid, rubric)
        n_q = self.brain.agenda.max_questions if self.brain.agenda else 8
        await self.send(P.RubricMessage(role_title=rubric.get("role_title", ""), competencies=self.brain.rubric_chips(), n_questions=n_q))
        target = self.brain.next_target()
        if target is None:
            await self.error(P.ErrorCode.INTERNAL, "rubric produced nothing to ask", fatal=True)
            return
        question = await self.brain.word_question(target)
        await self.ask(question, target, lead_in=self.brain.opener_text())

    async def ask(self, question: dict[str, Any], target: dict[str, Any], lead_in: str = "") -> None:
        assert self.brain and self.sid
        turn = self.brain.commit_question(question, target)
        log.info("%s %s [%s/%s] %s", self.sid, question["question_id"], target.get("competency_id"), target.get("strategy"), question["text"][:90])
        self.turn = turn
        self.turn_db_ids[turn.idx] = self.db.add_turn(self.sid, turn.idx, question)
        why = question["why"]
        await self.send(P.QuestionMessage(
            id=question["question_id"], text=question["text"],
            why=P.WhyTrace(competency_id=why["competency_id"], jd_quote=why["jd_quote"] or "(no quote)", ladder_rung=why["ladder_rung"],
                           strategy=why["strategy"], triggered_by=P.TriggeredBy(**why["triggered_by"]) if why.get("triggered_by") else None),
            time_limit_s=question.get("time_limit_s"),
        ))
        text = f"{lead_in} {question['text']}".strip()
        await self.speak(text)
        await self.listen()

    async def listen(self) -> None:
        self.set_state(P.SessionState.LISTENING)
        self.detector.reset()
        self.turn_started_at = time.monotonic()
        limit = (self.turn.question.get("time_limit_s") if self.turn else None)
        if self.timer_task:
            self.timer_task.cancel()
        if limit:
            self.timer_task = asyncio.create_task(self._timeout(limit + max(0.0, self.echo_gate_until - time.monotonic())))

    async def _timeout(self, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        try:
            await self._on_timeout()
        except Exception:  # noqa: BLE001
            log.exception("timeout handler failed")

    async def _on_timeout(self) -> None:
        if self.state is not P.SessionState.LISTENING or not self.detector.in_speech and self.detector.speech_t == 0:
            # nothing said yet: keep listening a little longer, then treat as an empty answer
            await asyncio.sleep(5.0)
            if self.state is not P.SessionState.LISTENING:
                return
        ev = self.detector.force_end()
        if self.pressure is P.Pressure.TOUGH:
            await self.send(P.InterruptMessage())
            self.set_state(P.SessionState.INTERRUPT)
            await self.speak(self.brain.interrupt_line("timeout") if self.brain else "Let me stop you there.")
        await self.send(P.VadMessage(state="speech_end"))
        audio = ev.audio if ev and ev.audio is not None else np.zeros(0, dtype=np.float32)
        await self.on_answer(audio)

    # ------------------------------------------------------------------ audio in
    async def on_audio(self, data: bytes) -> None:
        if not self.hello:
            return
        a = self.hello.audio_in
        if self.hello.needs_resample:
            data = to_16k_pcm16(data, a.sr, "f32le" if a.fmt == "f32" else "pcm16", a.ch)
        now = time.monotonic()
        if self.state is P.SessionState.ASKING:
            if self.pressure is P.Pressure.TOUGH and self.barge.feed_pcm16(data):
                await self.barge_in()
            return
        if self.state is not P.SessionState.LISTENING or now < self.echo_gate_until or self.ptt_down and False:
            return
        for ev in self.detector.feed_pcm16(data):
            if ev.kind == "speech_start":
                await self.send(P.VadMessage(state="speech_start"))
                self._start_nods()
            elif ev.kind == "speech_end":
                self._stop_nods()
                await self.send(P.VadMessage(state="speech_end"))
                if self.timer_task:
                    self.timer_task.cancel()
                self.answer_end_wall = time.monotonic()
                asyncio.create_task(self.on_answer(ev.audio))
            elif ev.kind == "speech_discard":
                self._stop_nods()
                await self.send(P.VadMessage(state="speech_end"))

    def _start_nods(self) -> None:
        if self.pressure is P.Pressure.TOUGH or self.nod_task:
            return

        async def nods() -> None:
            import random

            try:
                while self.state is P.SessionState.LISTENING:
                    await asyncio.sleep(random.uniform(*NOD_EVERY_S))
                    if self.detector.in_speech:
                        await self.send(P.ReactionMessage(mood="neutral", nod=True))
            except asyncio.CancelledError:
                pass

        self.nod_task = asyncio.create_task(nods())

    def _stop_nods(self) -> None:
        if self.nod_task:
            self.nod_task.cancel()
            self.nod_task = None

    async def barge_in(self) -> None:
        self.tts_cancel.set()
        if self.tts_task:
            self.tts_task.cancel()
        await self.send(P.InterruptMessage())
        self.set_state(P.SessionState.INTERRUPT)
        self.echo_gate_until = 0.0
        await self.listen()

    # ------------------------------------------------------------------ answer → brain
    async def on_answer(self, audio: np.ndarray) -> None:
        try:
            await self._on_answer(audio)
        except Exception as exc:  # noqa: BLE001 - a detached task must never die silently
            log.exception("on_answer failed")
            await self.error(P.ErrorCode.INTERNAL, f"turn failed: {exc!s}"[:300])

    async def _on_answer(self, audio: np.ndarray) -> None:
        if self.state in (P.SessionState.ANALYSING, P.SessionState.PLANNING, P.SessionState.WRAP):
            return
        assert self.brain and self.turn and self.sid and self.models.stt
        self.set_state(P.SessionState.ANALYSING)
        turn = self.turn
        clip_path = None
        if audio.size:
            d = _env.DATA_DIR / "sessions" / self.sid
            d.mkdir(parents=True, exist_ok=True)
            clip_path = str(d / f"{turn.idx}.wav")
            sf.write(clip_path, audio, 16000, subtype="PCM_16")
        turn.clip_path, turn.duration_s = clip_path, len(audio) / 16000
        transcript = await asyncio.to_thread(self.models.stt.transcribe, audio, 16000) if audio.size else None
        text = transcript.text if transcript else ""
        words = transcript.word_dicts() if transcript else []
        await self.send(P.SttMessage(text=text or "(no speech detected)", final=True))
        log.info("%s %s: %.1fs audio, %d words, stt %.0f ms", self.sid, turn.answer_id, turn.duration_s, len(words), transcript.latency_ms if transcript else 0)
        # §5.3 critical-path trick: the candidate never waits for analysis. Word the provisional
        # next question from the coverage matrix + a vagueness heuristic and speak it now; Stage C
        # runs in the background and folds into the agenda, so a demanded follow-up becomes the
        # question after this one (and the reaction/mood lands while the candidate listens).
        # LM Studio runs with --parallel 1, so requests are served strictly in arrival order: the
        # provisional question (Stage B, ~150 tokens) must be requested BEFORE Stage C (~600 tokens)
        # or it queues behind it and the candidate waits ~10 s (measured in e2e round 3).
        prov_target = self.brain.provisional_target(text)
        stop, reason = self.brain.should_stop()
        if prov_target is None or stop or self.brain.agenda.total_asked >= self.brain.agenda.max_questions:
            analysis, gate, _ = await self.brain.analyse(turn, text, words)
            await self._after_analysis(turn, analysis, gate, text, words, audio, clip_path)
            await self.finish_round(reason=reason or "done")
            return
        t0 = time.perf_counter()
        question = await self.brain.word_question(prov_target)
        log.info("%s stage B (provisional %s) %.0f ms", self.sid, prov_target.competency_id if hasattr(prov_target, "competency_id") else prov_target, (time.perf_counter() - t0) * 1000)
        analysis_task = asyncio.create_task(self.brain.analyse(turn, text, words))
        lead = self.brain.reaction_line("neutral")
        asyncio.create_task(self._finish_analysis(turn, analysis_task, text, words, audio, clip_path))
        await self.ask(question, prov_target, lead_in=lead)

    async def _finish_analysis(self, turn: Turn, analysis_task: "asyncio.Task", text: str, words: list, audio: np.ndarray, clip_path: str | None) -> None:
        try:
            analysis, gate, _pending = await analysis_task
            await self._after_analysis(turn, analysis, gate, text, words, audio, clip_path)
        except Exception:  # noqa: BLE001
            log.exception("background analysis failed")

    async def _after_analysis(self, turn: Turn, analysis: dict[str, Any], gate: Any, text: str, words: list, audio: np.ndarray, clip_path: str | None) -> None:
        assert self.brain
        prosody = answer_delivery(turn.answer_id, words, turn.duration_s, turn.question.get("time_limit_s"), audio if audio.size else None)
        turn.prosody = prosody
        self.per_answer.append(prosody)
        self.hedges += count_hedges(text) + len(analysis.get("hedges") or [])
        kw = analysis.get("jd_keyword_coverage") or {}
        self.kw_hit += kw.get("hit", [])
        self.kw_missed += kw.get("missed", [])
        self.db.finish_turn(self.turn_db_ids[turn.idx], text, words, analysis, prosody, clip_path)
        mood = self.brain.reaction_for(analysis)
        log.info("%s %s: verdict=%s mood=%s next=%s dropped=%d", self.sid, turn.answer_id, analysis.get("verdict"), mood, analysis.get("next_strategy"), len(gate.dropped))
        await self.send(P.ReactionMessage(mood=mood, nod=analysis.get("verdict") in ("strong", "adequate")))

    async def finish_round(self, reason: str = "done") -> None:
        assert self.brain and self.sid
        self.set_state(P.SessionState.WRAP)
        if self.timer_task:
            self.timer_task.cancel()
        await self.speak(prompts.CLOSING_LINE)
        delivery = aggregate(self.per_answer, self.hedges, self.kw_hit, self.kw_missed)
        try:
            report = await self.brain.build_report(delivery)
        except Exception as exc:  # noqa: BLE001
            log.exception("Stage D failed")
            await self.error(P.ErrorCode.INTERNAL, f"report failed: {exc!s}"[:300])
            report = {"error": str(exc), "delivery": delivery}
        report["latency_ms"] = [round(x * 1000) for x in self.latencies]
        report["stop_reason"] = reason
        self.db.save_report(self.sid, report)
        self.db.end_session(self.sid, "completed")
        self.set_state(P.SessionState.REPORT)
        await self.send(P.ReportMessage(url=self.app.report_url(self.sid), session=self.sid))

    # ------------------------------------------------------------------ audio out
    async def speak(self, text: str) -> None:
        """Stream Kokoro audio + visemes: tts_start · [viseme…, frames…]* · tts_end."""
        assert self.models.tts
        self.set_state(P.SessionState.ASKING)
        self.tts_cancel = threading.Event()
        cancel = self.tts_cancel
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()

        def producer() -> None:
            try:
                for chunk in self.models.tts.stream(text):
                    if cancel.is_set():
                        break
                    loop.call_soon_threadsafe(q.put_nowait, chunk)
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(q.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        threading.Thread(target=producer, daemon=True).start()
        self.tts_started_at = time.monotonic()
        self.tts_audio_s = 0.0
        self.barge.reset()
        first = True
        await self.send(P.TtsStartMessage(sr=P.OUT_SR))
        if self.answer_end_wall:
            self.latencies.append(time.monotonic() - self.answer_end_wall)
            self.answer_end_wall = 0.0
        while True:
            chunk = await q.get()
            if chunk is None:
                break
            if isinstance(chunk, Exception):
                log.error("tts failed: %r", chunk)
                break
            if cancel.is_set():
                break
            for ev in chunk.visemes:
                await self.send(P.VisemeMessage(t_ms=int(ev["t_ms"]), id=int(ev["id"])))
            pcm = chunk.pcm16
            for i in range(0, len(pcm), P.OUT_FRAME_BYTES):
                await self.send_bytes(pcm[i : i + P.OUT_FRAME_BYTES])
            self.tts_audio_s += len(chunk.audio) / P.OUT_SR
            first = False
        await self.send(P.TtsEndMessage())
        playback_end = self.tts_started_at + self.tts_audio_s
        self.echo_gate_until = max(time.monotonic(), playback_end) + ECHO_GATE_S


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:  # noqa: BLE001
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:  # noqa: BLE001
            return "127.0.0.1"


class App:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.models = Models()
        self.db = DB(_env.DATA_DIR / "interview.sqlite")
        self.sync = SupabaseSync(self.db, _env.DATA_DIR, server_version=VERSION)
        self.token = args.token or os.environ.get("SESSION_TOKEN_SECRET") or secrets.token_hex(16)
        self.sessions: dict[int, Session] = {}
        self.started = time.time()
        self.ip = lan_ip()

    def pair_payload(self) -> dict[str, Any]:
        url = f"interviewcracker://pair?h={self.ip}&p={self.args.port}&t={self.token}&v=1"
        d = {"host": self.ip, "port": self.args.port, "token": self.token, "url": url, "manual": f"{self.ip}:{self.args.port}:{self.token}",
             "ws": f"ws://{self.ip}:{self.args.port}/ws"}
        if self.args.emulator:
            d["emulator_ws"] = f"ws://10.0.2.2:{self.args.port}/ws"
            d["emulator_manual"] = f"10.0.2.2:{self.args.port}:{self.token}"
        return d

    def report_url(self, sid: str) -> str:
        return f"http://{self.ip}:{self.args.port}/report/{sid}"


def build_app(app_state: App) -> FastAPI:
    api = FastAPI(title="Interview Cracker voice server", version=VERSION)
    static_dir = SERVER_DIR / "static"
    static_dir.mkdir(exist_ok=True)
    api.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @api.get("/health")
    def health() -> dict[str, Any]:
        mem = _env.gpu_mem_mib()
        return {"status": "ok", "version": VERSION, "uptime_s": round(time.time() - app_state.started, 1),
                "models": app_state.models.info, "vram_mib": mem[0] if mem else None, "sessions_active": len(app_state.sessions),
                "sync": app_state.sync.status()}

    @api.get("/pair.json")
    def pair_json() -> dict[str, Any]:
        return app_state.pair_payload()

    @api.get("/pair", response_class=HTMLResponse)
    def pair() -> str:
        import qrcode

        p = app_state.pair_payload()
        img = qrcode.make(p["url"])
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        emu = f"<p>Emulator: <code>{p['emulator_manual']}</code> (<code>{p['emulator_ws']}</code>)</p>" if "emulator_manual" in p else ""
        return f"""<!doctype html><html><head><meta charset="utf-8"><title>Interview Cracker — pair</title>
<style>body{{font-family:system-ui;margin:2rem;max-width:720px}}code{{background:#eee;padding:2px 6px;border-radius:4px}}img{{width:320px;height:320px;image-rendering:pixelated}}</style></head>
<body><h1>Pair your phone</h1><img src="data:image/png;base64,{b64}" alt="QR">
<p>Scan with the app, or type <code>{p['manual']}</code></p><p>WebSocket: <code>{p['ws']}</code></p>{emu}
<p><a href="/static/test.html">Browser test client</a> · <a href="/health">health</a> · <a href="/sessions">sessions</a></p></body></html>"""

    @api.get("/sessions")
    def sessions() -> list[dict[str, Any]]:
        return [{k: v for k, v in s.items() if k not in ("jd_text", "rubric")} for s in app_state.db.list_sessions()]

    @api.get("/report/{sid}")
    def report(sid: str) -> JSONResponse:
        s = app_state.db.get_session(sid)
        if not s:
            raise HTTPException(404, "unknown session")
        turns = app_state.db.get_turns(sid)
        for t in turns:
            t["clip_url"] = f"http://{app_state.ip}:{app_state.args.port}/clips/{sid}/{t['idx']}.wav" if t.get("clip_path") else None
        rep = app_state.db.get_report(sid)
        return JSONResponse({"session": s, "turns": turns, "report": rep.get("report") if rep else None})

    @api.get("/report/{sid}/view", response_class=HTMLResponse)
    def report_view(sid: str) -> str:
        data = json.loads(report(sid).body)
        rep = data.get("report") or {}
        turns = {t["idx"]: t for t in data["turns"]}
        fixes = "".join(
            f"<li><b>{f.get('behaviour','')}</b> — “{f.get('quote','')}” <small>({f.get('answer_id')}, {f.get('t',[0,0])[0]:.1f}s)</small>"
            f"<br><i>{f.get('why_it_matters','')}</i><br>Stronger: {f.get('stronger_version','')}"
            + (f"<br><audio controls src='{turns[int(f['answer_id'][1:])]['clip_url']}#t={f.get('t',[0,0])[0]:.1f}'></audio>" if f.get('answer_id') and int(f['answer_id'][1:]) in turns and turns[int(f['answer_id'][1:])].get('clip_url') else "")
            + "</li>" for f in rep.get("top_fixes", []))
        rows = "".join(f"<tr><td>{r['competency_id']}</td><td>{r['name']}</td><td>{r['priority']}</td><td>{', '.join(c['evidence_item']+'='+c['level'] for c in r['cells'])}</td></tr>" for r in (rep.get("coverage_matrix") or {}).get("rows", []))
        qs = "".join(f"<li><b>{t['question'].get('text','')}</b><br><small>why: {t['question'].get('why',{}).get('jd_quote','')}</small><br>{t.get('transcript','')}</li>" for t in data["turns"])
        return f"""<!doctype html><html><head><meta charset="utf-8"><title>Report {sid}</title><style>body{{font-family:system-ui;margin:2rem;max-width:900px}}table{{border-collapse:collapse}}td{{border:1px solid #ccc;padding:4px 8px}}</style></head>
<body><h1>Report {sid}</h1><p>Band: <b>{rep.get('overall_band','?')}</b> — {rep.get('band_mover','')}</p>
<h2>Top fixes</h2><ol>{fixes or '<li>(none)</li>'}</ol><h2>Coverage</h2><table>{rows}</table><h2>Questions</h2><ol>{qs}</ol>
<h2>Delivery</h2><pre>{json.dumps(rep.get('delivery'), indent=1)}</pre></body></html>"""

    @api.get("/clips/{sid}/{idx}.wav")
    def clip(sid: str, idx: int) -> FileResponse:
        p = _env.DATA_DIR / "sessions" / sid / f"{idx}.wav"
        if not p.exists():
            raise HTTPException(404, "no clip")
        return FileResponse(str(p), media_type="audio/wav")

    @api.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        session = Session(ws, app_state)
        await session.run()

    return api


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--emulator", action="store_true", help="also print the 10.0.2.2 pairing line for the Android emulator")
    ap.add_argument("--token", default=os.environ.get("SESSION_TOKEN"), help="fixed pairing token (default: random)")
    ap.add_argument("--stt", choices=["cuda", "cpu"], default="cuda")
    ap.add_argument("--tts-device", choices=["cuda", "cpu"], default="cuda")
    ap.add_argument("--voice", default=os.environ.get("KOKORO_VOICE", "af_heart"))
    ap.add_argument("--tts-backend", choices=["kokoro", "gemini"], default=os.environ.get("TTS_BACKEND", "kokoro"),
                    help="kokoro = local (default); gemini = Google Gemini TTS via GEMINI_API_KEY (cloud, optional)")
    ap.add_argument("--gemini-voice", default=os.environ.get("GEMINI_TTS_VOICE", "Kore"))
    ap.add_argument("--llm-model", default=os.environ.get("LMSTUDIO_MODEL", "interviewer"))
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app_state = App(args)
    app_state.models.load(args)
    app_state.sync.start()
    p = app_state.pair_payload()
    print("=" * 64)
    print(f"Interview Cracker server {VERSION}  ·  {app_state.models.info}")
    print(f"PAIR  : http://localhost:{args.port}/pair")
    print(f"MANUAL: {p['manual']}")
    print(f"WS    : {p['ws']}")
    if args.emulator:
        print(f"EMU   : {p['emulator_manual']}   ({p['emulator_ws']})")
    print(f"TEST  : http://localhost:{args.port}/static/test.html")
    print("READY")
    print("=" * 64, flush=True)
    import uvicorn

    uvicorn.run(build_app(app_state), host=args.host, port=args.port, log_level="warning", ws_max_size=4 * 1024 * 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
