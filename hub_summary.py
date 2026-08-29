"""Kunlik hub xulosasi — Martekovka."""

from __future__ import annotations

from storage import Session, live_work_seconds


def fmt_clock(seconds: int) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def session_summary(ws: Session) -> str:
    ish = fmt_clock(live_work_seconds(ws))
    dam = fmt_clock(ws.pause_sec)
    return f"Martekovka: poz {ws.poz}, ish {ish}, dam {dam}"


def daily_summary(sessions: list[Session]) -> str:
    if not sessions:
        return "Martekovka: poz 0, ish 00:00:00, dam 00:00:00"
    total_poz = sum(int(s.poz or 0) for s in sessions)
    total_ish = sum(int(s.work_sec or 0) for s in sessions)
    total_dam = sum(int(s.pause_sec or 0) for s in sessions)
    return (
        f"Martekovka: poz {total_poz}, ish {fmt_clock(total_ish)}, dam {fmt_clock(total_dam)}"
    )
