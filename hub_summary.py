"""Kunlik hub xulosasi — Martekovka."""

from __future__ import annotations

from storage import NORM_SEC_PER_POZ, Session, calc_points, live_work_seconds


def fmt_clock(seconds: int) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def session_summary(ws: Session) -> str:
    work = ws.work_sec if ws.status != "active" else live_work_seconds(ws)
    ish = fmt_clock(work)
    return f"Markerovka: poz {ws.poz}, ish {ish}, norm {NORM_SEC_PER_POZ}s"


def daily_summary(sessions: list[Session]) -> str:
    if not sessions:
        return "Markerovka: poz 0, ish 00:00:00, norm 20s"
    total_poz = sum(int(s.poz or 0) for s in sessions)
    total_ish = sum(int(s.work_sec or 0) for s in sessions)
    return f"Markerovka: poz {total_poz}, ish {fmt_clock(total_ish)}, norm {NORM_SEC_PER_POZ}s"
