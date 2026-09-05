"""Supabase outbox worker: flushes sessions/turns/reports/clips when the laptop is online.

Never on the request path. Runs in a daemon thread, wakes every ``interval_s``, checks
reachability with a cheap HEAD, then drains ``sync_outbox`` in FK order with exponential
backoff per row. ``SUPABASE_MODE=off`` disables it. The service-role key bypasses RLS, so
the server can write guest rows (user_id NULL + device_id) that only the owner can claim.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from store.db import DB

log = logging.getLogger("store.sync")

NS = uuid.UUID("6f1c2a9e-4d3b-4a1f-9c6e-0b8f1d2e3a4b")  # namespace for deterministic cloud ids


def cloud_id(local_id: str) -> str:
    return str(uuid.uuid5(NS, f"interviewcracker:{local_id}"))


def jd_cloud_id(device_id: str, jd_text: str) -> str:
    return str(uuid.uuid5(NS, f"jd:{device_id}:{hashlib.sha256(jd_text.encode('utf-8')).hexdigest()}"))


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def load_device_id(data_dir: Path) -> str:
    """A 32-hex secret that stamps guest rows so the laptop owner can claim them later."""
    p = data_dir / "device_id.txt"
    if p.exists():
        v = p.read_text(encoding="utf-8").strip()
        if len(v) >= 32:
            return v
    v = uuid.uuid4().hex
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(v, encoding="utf-8")
    return v


class SupabaseSync:
    def __init__(self, db: DB, data_dir: Path, mode: str | None = None, url: str | None = None, key: str | None = None,
                 interval_s: float = 15.0, server_version: str = "0.1.0"):
        self.db = db
        self.data_dir = data_dir
        self.mode = (mode or os.environ.get("SUPABASE_MODE", "off")).lower()
        self.url = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key = key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.interval_s = interval_s
        self.server_version = server_version
        self.device_id = load_device_id(data_dir)
        self.enabled = self.mode in ("cloud", "selfhosted") and bool(self.url) and bool(self.key)
        self.online = False
        self.last_flush: dict[str, Any] = {}
        self._client = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if self.mode != "off" and not self.enabled:
            log.warning("SUPABASE_MODE=%s but SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY missing — sync disabled", self.mode)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if not self.enabled or self._thread:
            return
        self._thread = threading.Thread(target=self._loop, name="supabase-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, Any]:
        return {"mode": self.mode, "enabled": self.enabled, "online": self.online, "pending": len(self.db.pending(1000)) if self.enabled else None,
                "last_flush": self.last_flush, "device_id_prefix": self.device_id[:6] + "…"}

    # ------------------------------------------------------------------ internals
    def _reachable(self) -> bool:
        import httpx

        try:
            r = httpx.head(f"{self.url}/rest/v1/", headers={"apikey": self.key}, timeout=3.0)
            return r.status_code < 500
        except Exception:  # noqa: BLE001
            return False

    def _sb(self):
        if self._client is None:
            from supabase import create_client

            self._client = create_client(self.url, self.key)
        return self._client

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                self.online = self._reachable()
                if self.online:
                    self.flush()
            except Exception as exc:  # noqa: BLE001
                log.warning("sync loop error: %r", exc)

    # ------------------------------------------------------------------ flush
    def flush(self, limit: int = 50) -> dict[str, int]:
        """Drain the outbox in FK order. Returns counts per kind."""
        order = {"session": 0, "turn": 1, "report": 2, "clip": 3}
        rows = sorted(self.db.pending(limit), key=lambda r: (order.get(r["kind"], 9), r["id"]))
        done = {"session": 0, "turn": 0, "report": 0, "clip": 0, "failed": 0}
        for row in rows:
            try:
                handler = getattr(self, f"_push_{row['kind']}")
                handler(row)
                self.db.mark_done(row["id"])
                done[row["kind"]] += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("sync %s %s failed (attempt %d): %r", row["kind"], row["ref_id"], row["attempts"], exc)
                self.db.mark_failed(row["id"], row["attempts"])
                done["failed"] += 1
        self.last_flush = {"at": time.time(), **done}
        return done

    def _push_session(self, row: dict[str, Any]) -> None:
        s = self.db.get_session(row["ref_id"])
        if not s:
            return
        sb = self._sb()
        jd_id = jd_cloud_id(self.device_id, s["jd_text"])
        title = (s.get("rubric") or {}).get("role_title") or s["jd_text"].strip().splitlines()[0][:80]
        sb.table("jds").upsert(
            {"id": jd_id, "user_id": None, "device_id": self.device_id, "title": title, "raw_text": s["jd_text"], "rubric": s.get("rubric")},
            on_conflict="id", ignore_duplicates=True,
        ).execute()
        if s.get("rubric"):
            sb.table("jds").update({"rubric": s["rubric"]}).eq("id", jd_id).is_("user_id", "null").execute()
        sid = cloud_id(s["id"])
        sb.table("sessions").upsert(
            {"id": sid, "user_id": None, "device_id": self.device_id, "jd_id": jd_id, "pressure": s["pressure"], "status": s["status"],
             "started_at": _iso(s.get("started_at")), "ended_at": _iso(s.get("ended_at")), "device_info": s.get("device_info") or {},
             "server_version": s.get("server_version") or self.server_version},
            on_conflict="id", ignore_duplicates=True,
        ).execute()
        # never re-send user_id / device_id / claimed_at on an update (would un-claim an adopted row)
        sb.table("sessions").update({"status": s["status"], "ended_at": _iso(s.get("ended_at"))}).eq("id", sid).execute()

    def _push_turn(self, row: dict[str, Any]) -> None:
        t = self.db.get_turn(row["ref_id"])
        if not t:
            return
        self._sb().table("turns").upsert(
            {"id": cloud_id(t["id"]), "session_id": cloud_id(t["session_id"]), "idx": t["idx"], "question": t.get("question"),
             "transcript": t.get("transcript"), "words": t.get("words"), "analysis": t.get("analysis"),
             "started_at": _iso(t.get("started_at")), "ended_at": _iso(t.get("ended_at"))},
            on_conflict="id",
        ).execute()

    def _push_report(self, row: dict[str, Any]) -> None:
        r = self.db.get_report(row["ref_id"])
        if not r:
            return
        self._sb().table("reports").upsert(
            {"id": cloud_id(r["id"]), "session_id": cloud_id(r["session_id"]), "report": r["report"]}, on_conflict="session_id",
        ).execute()

    def _push_clip(self, row: dict[str, Any]) -> None:
        t = self.db.get_turn(row["ref_id"])
        if not t or not t.get("clip_path") or not Path(t["clip_path"]).exists():
            return
        sid = cloud_id(t["session_id"])
        path = f"guest/{sid}/{t['idx']}.wav"
        data = Path(t["clip_path"]).read_bytes()
        self._sb().storage.from_("clips").upload(path, data, {"content-type": "audio/wav", "upsert": "true"})
        self._sb().table("turns").update({"clip_path": path}).eq("id", cloud_id(t["id"])).execute()
