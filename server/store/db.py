"""SQLite store: sessions, turns, reports, and a sync outbox for Supabase (BLUEPRINT §8.1).

Everything the live loop needs is local. JSON columns are stored as text. WAL mode so the
sync worker can read while the session writes.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = """
create table if not exists sessions (
  id text primary key,
  jd_id text,
  jd_text text not null,
  rubric_json text,
  pressure text not null,
  voice text,
  status text not null default 'created',
  device_id text,
  device_info_json text,
  server_version text,
  started_at real not null,
  ended_at real
);
create table if not exists turns (
  id text primary key,
  session_id text not null references sessions(id) on delete cascade,
  idx integer not null,
  question_json text not null,
  transcript text,
  words_json text,
  analysis_json text,
  prosody_json text,
  clip_path text,
  started_at real,
  ended_at real,
  unique(session_id, idx)
);
create table if not exists reports (
  id text primary key,
  session_id text not null unique references sessions(id) on delete cascade,
  report_json text not null,
  created_at real not null
);
create table if not exists sync_outbox (
  id integer primary key autoincrement,
  kind text not null,            -- session | turn | report | clip
  ref_id text not null,
  payload_json text,
  attempts integer not null default 0,
  next_attempt_at real not null default 0,
  done integer not null default 0,
  created_at real not null
);
create index if not exists idx_turns_session on turns(session_id, idx);
create index if not exists idx_outbox_pending on sync_outbox(done, next_attempt_at);
"""


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class DB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("pragma journal_mode=wal")
        self._conn.execute("pragma foreign_keys=on")
        self._conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ helpers
    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    @staticmethod
    def _j(obj: Any) -> str | None:
        return None if obj is None else json.dumps(obj, ensure_ascii=False)

    @staticmethod
    def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
        if r is None:
            return None
        d = dict(r)
        for k in list(d):
            if k.endswith("_json") and d[k]:
                d[k[:-5]] = json.loads(d[k])
                del d[k]
        return d

    # ------------------------------------------------------------------ sessions
    def create_session(self, jd_text: str, pressure: str, voice: str | None, device_id: str | None = None,
                       device_info: dict | None = None, server_version: str = "0.1.0") -> str:
        sid = new_id("s_")
        self._exec(
            "insert into sessions(id, jd_text, pressure, voice, status, device_id, device_info_json, server_version, started_at) values (?,?,?,?,?,?,?,?,?)",
            (sid, jd_text, pressure, voice, "created", device_id, self._j(device_info), server_version, time.time()),
        )
        self.enqueue("session", sid)
        return sid

    def set_rubric(self, sid: str, rubric: dict, jd_id: str | None = None) -> None:
        self._exec("update sessions set rubric_json=?, jd_id=coalesce(?, jd_id), status='live' where id=?", (self._j(rubric), jd_id, sid))
        self.enqueue("session", sid)

    def end_session(self, sid: str, status: str = "completed") -> None:
        self._exec("update sessions set status=?, ended_at=? where id=?", (status, time.time(), sid))
        self.enqueue("session", sid)

    def get_session(self, sid: str) -> dict[str, Any] | None:
        return self._row(self._exec("select * from sessions where id=?", (sid,)).fetchone())

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        return [self._row(r) for r in self._exec("select * from sessions order by started_at desc limit ?", (limit,)).fetchall()]

    # ------------------------------------------------------------------ turns
    def add_turn(self, sid: str, idx: int, question: dict) -> str:
        tid = new_id("t_")
        self._exec(
            "insert into turns(id, session_id, idx, question_json, started_at) values (?,?,?,?,?)",
            (tid, sid, idx, self._j(question), time.time()),
        )
        return tid

    def finish_turn(self, tid: str, transcript: str, words: list[dict], analysis: dict | None, prosody: dict | None, clip_path: str | None) -> None:
        self._exec(
            "update turns set transcript=?, words_json=?, analysis_json=?, prosody_json=?, clip_path=?, ended_at=? where id=?",
            (transcript, self._j(words), self._j(analysis), self._j(prosody), clip_path, time.time(), tid),
        )
        self.enqueue("turn", tid)
        if clip_path:
            self.enqueue("clip", tid, {"clip_path": clip_path})

    def set_turn_analysis(self, tid: str, analysis: dict) -> None:
        self._exec("update turns set analysis_json=? where id=?", (self._j(analysis), tid))
        self.enqueue("turn", tid)

    def get_turns(self, sid: str) -> list[dict[str, Any]]:
        return [self._row(r) for r in self._exec("select * from turns where session_id=? order by idx", (sid,)).fetchall()]

    def get_turn(self, tid: str) -> dict[str, Any] | None:
        return self._row(self._exec("select * from turns where id=?", (tid,)).fetchone())

    # ------------------------------------------------------------------ reports
    def save_report(self, sid: str, report: dict) -> str:
        rid = new_id("r_")
        self._exec(
            "insert into reports(id, session_id, report_json, created_at) values (?,?,?,?) on conflict(session_id) do update set report_json=excluded.report_json, created_at=excluded.created_at",
            (rid, sid, self._j(report), time.time()),
        )
        self.enqueue("report", sid)
        return rid

    def get_report(self, sid: str) -> dict[str, Any] | None:
        return self._row(self._exec("select * from reports where session_id=?", (sid,)).fetchone())

    # ------------------------------------------------------------------ outbox
    def enqueue(self, kind: str, ref_id: str, payload: dict | None = None) -> None:
        self._exec(
            "insert into sync_outbox(kind, ref_id, payload_json, created_at) values (?,?,?,?)",
            (kind, ref_id, self._j(payload), time.time()),
        )

    def pending(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._exec(
            "select * from sync_outbox where done=0 and next_attempt_at<=? order by id limit ?", (time.time(), limit)
        ).fetchall()
        return [self._row(r) for r in rows]

    def mark_done(self, outbox_id: int) -> None:
        self._exec("update sync_outbox set done=1 where id=?", (outbox_id,))

    def mark_failed(self, outbox_id: int, attempts: int) -> None:
        delay = min(600, 5 * (2 ** attempts))
        self._exec("update sync_outbox set attempts=?, next_attempt_at=? where id=?", (attempts + 1, time.time() + delay, outbox_id))

    def close(self) -> None:
        with self._lock:
            self._conn.close()
