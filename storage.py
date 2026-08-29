"""Martekovka sessiyalari — SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import os

TZ = ZoneInfo(os.getenv("TZ", "Asia/Tashkent"))


@dataclass
class Session:
    id: int
    tg_id: int
    day: str
    status: str
    started_at: str
    work_sec: int
    pause_sec: int
    poz: int
    tick_at: str | None


def _conn(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def init_db(db_path: str) -> None:
    con = _conn(db_path)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            tick_at TEXT,
            work_sec INTEGER NOT NULL DEFAULT 0,
            pause_sec INTEGER NOT NULL DEFAULT 0,
            poz INTEGER NOT NULL DEFAULT 0,
            ended_at TEXT,
            hub_pushed INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_tg ON sessions(tg_id, day)")
    con.commit()
    con.close()


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now(TZ).date().isoformat()


def _row_to_session(row: sqlite3.Row | None) -> Session | None:
    if not row:
        return None
    return Session(
        id=int(row["id"]),
        tg_id=int(row["tg_id"]),
        day=str(row["day"]),
        status=str(row["status"]),
        started_at=str(row["started_at"]),
        work_sec=int(row["work_sec"] or 0),
        pause_sec=int(row["pause_sec"] or 0),
        poz=int(row["poz"] or 0),
        tick_at=str(row["tick_at"]) if row["tick_at"] else None,
    )


def get_open_session(db_path: str, tg_id: int) -> Session | None:
    con = _conn(db_path)
    row = con.execute(
        """
        SELECT * FROM sessions
        WHERE tg_id = ? AND status IN ('active', 'paused', 'awaiting_qty')
        ORDER BY id DESC LIMIT 1
        """,
        (int(tg_id),),
    ).fetchone()
    con.close()
    return _row_to_session(row)


def start_session(db_path: str, tg_id: int) -> Session:
    now = _now()
    day = _today()
    con = _conn(db_path)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO sessions(tg_id, day, status, started_at, tick_at)
        VALUES (?, ?, 'active', ?, ?)
        """,
        (int(tg_id), day, now, now),
    )
    sid = int(cur.lastrowid)
    con.commit()
    row = con.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    con.close()
    return _row_to_session(row)  # type: ignore[return-value]


def _elapsed_since(tick_at: str | None) -> int:
    if not tick_at:
        return 0
    try:
        t0 = datetime.strptime(tick_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        return max(0, int((datetime.now(TZ) - t0).total_seconds()))
    except ValueError:
        return 0


def pause_session(db_path: str, tg_id: int) -> Session | None:
    ws = get_open_session(db_path, tg_id)
    if not ws or ws.status != "active":
        return None
    extra = _elapsed_since(ws.tick_at)
    con = _conn(db_path)
    con.execute(
        """
        UPDATE sessions SET status = 'paused', work_sec = work_sec + ?, tick_at = NULL
        WHERE id = ?
        """,
        (extra, ws.id),
    )
    con.commit()
    row = con.execute("SELECT * FROM sessions WHERE id = ?", (ws.id,)).fetchone()
    con.close()
    return _row_to_session(row)


def resume_session(db_path: str, tg_id: int) -> Session | None:
    ws = get_open_session(db_path, tg_id)
    if not ws or ws.status != "paused":
        return None
    now = _now()
    con = _conn(db_path)
    con.execute(
        "UPDATE sessions SET status = 'active', tick_at = ? WHERE id = ?",
        (now, ws.id),
    )
    con.commit()
    row = con.execute("SELECT * FROM sessions WHERE id = ?", (ws.id,)).fetchone()
    con.close()
    return _row_to_session(row)


def request_finish(db_path: str, tg_id: int) -> Session | None:
    ws = get_open_session(db_path, tg_id)
    if not ws or ws.status not in ("active", "paused"):
        return None
    extra = _elapsed_since(ws.tick_at) if ws.status == "active" else 0
    con = _conn(db_path)
    con.execute(
        """
        UPDATE sessions SET status = 'awaiting_qty', work_sec = work_sec + ?, tick_at = NULL
        WHERE id = ?
        """,
        (extra, ws.id),
    )
    con.commit()
    row = con.execute("SELECT * FROM sessions WHERE id = ?", (ws.id,)).fetchone()
    con.close()
    return _row_to_session(row)


def complete_finish(db_path: str, tg_id: int, poz: int) -> Session | None:
    ws = get_open_session(db_path, tg_id)
    if not ws or ws.status != "awaiting_qty":
        return None
    now = _now()
    con = _conn(db_path)
    con.execute(
        """
        UPDATE sessions SET status = 'done', poz = ?, ended_at = ?, hub_pushed = 0
        WHERE id = ?
        """,
        (int(poz), now, ws.id),
    )
    con.commit()
    row = con.execute("SELECT * FROM sessions WHERE id = ?", (ws.id,)).fetchone()
    con.close()
    return _row_to_session(row)


def mark_hub_pushed(db_path: str, session_id: int) -> None:
    con = _conn(db_path)
    con.execute("UPDATE sessions SET hub_pushed = 1 WHERE id = ?", (int(session_id),))
    con.commit()
    con.close()


def cancel_open(db_path: str, tg_id: int) -> bool:
    ws = get_open_session(db_path, tg_id)
    if not ws:
        return False
    con = _conn(db_path)
    con.execute("DELETE FROM sessions WHERE id = ?", (ws.id,))
    con.commit()
    con.close()
    return True


def live_work_seconds(ws: Session) -> int:
    extra = _elapsed_since(ws.tick_at) if ws.status == "active" else 0
    return int(ws.work_sec + extra)


def today_stats(db_path: str, tg_id: int) -> tuple[int, int, int]:
    """(sessiyalar, jami_poz, jami_ish_sec) — bugun tugagan."""
    day = _today()
    con = _conn(db_path)
    rows = con.execute(
        """
        SELECT poz, work_sec FROM sessions
        WHERE tg_id = ? AND day = ? AND status = 'done'
        """,
        (int(tg_id), day),
    ).fetchall()
    con.close()
    n = len(rows)
    poz = sum(int(r["poz"] or 0) for r in rows)
    sec = sum(int(r["work_sec"] or 0) for r in rows)
    return n, poz, sec


def today_done_sessions(db_path: str, tg_id: int) -> list[Session]:
    day = _today()
    con = _conn(db_path)
    rows = con.execute(
        """
        SELECT * FROM sessions
        WHERE tg_id = ? AND day = ? AND status = 'done'
        ORDER BY id ASC
        """,
        (int(tg_id), day),
    ).fetchall()
    con.close()
    return [_row_to_session(r) for r in rows if r]  # type: ignore[misc]
