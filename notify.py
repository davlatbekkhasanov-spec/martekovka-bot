"""Guruh va xodim xabarlari — mesta bot uslubida."""

from __future__ import annotations

import html
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

log = logging.getLogger(__name__)

_SEP = "━━━━━━━━━━━━━━━━━"


def _he(name: str) -> str:
    return html.escape((name or "Noma'lum").strip() or "Noma'lum")


def progress_bar(percent: float, *, width: int = 10, positive: bool = True) -> str:
    pct = max(0.0, min(100.0, percent))
    filled = int(round(pct / 100 * width))
    fill, empty = ("🟩", "⬜") if positive else ("🟥", "⬜")
    return fill * filled + empty * (width - filled)


def fmt_hm(dt_str: str) -> str:
    try:
        dt = datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%H:%M")
    except ValueError:
        return dt_str[:5] if dt_str else "—"


def fmt_duration_sec(seconds: int) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


async def send_group(bot: Bot, group_id: int, text: str) -> bool:
    if not group_id:
        log.warning("GROUP_ID yo'q — guruhga yuborilmadi")
        return False
    try:
        await bot.send_message(group_id, text)
        return True
    except TelegramAPIError as exc:
        log.error("Guruhga yuborish xato (%s): %s", group_id, exc)
        return False


def group_started_message(*, name: str) -> str:
    return f"🏷️  <b>{_he(name)}</b> markirovka ishlarini boshladi"


def group_finished_message(*, name: str, poz: int, points: int, photos: int, work_sec: int) -> str:
    return (
        f"🏁  <b>{_he(name)}</b> markirovka ishlarini yakunladi\n"
        f"📦 <b>{poz}</b> poz  ·  🏆 <b>{points}</b> ball  ·  "
        f"📷 <b>{photos}</b> rasm  ·  ⏱ <b>{fmt_duration_sec(work_sec)}</b>"
    )


def _finish_banner(*, poz: int, work_sec: int, norm_sec: int, points: int) -> tuple[str, str, str]:
    if poz <= 0:
        return "✅ <b>YAKUNLANDI</b> ✅", "", progress_bar(100, positive=True)

    if work_sec <= norm_sec:
        saved = norm_sec - work_sec
        pct = min(100.0, (saved / norm_sec * 100) if norm_sec else 100.0)
        if work_sec <= norm_sec // 2:
            banner = "🔥🔥 <b>AJOYIB! SUPER TEZ!</b> 🔥🔥"
        elif saved >= norm_sec * 0.2:
            banner = "🔥 <b>AJOYIB! VAQT TEJALDINGIZ!</b> 🔥"
        else:
            banner = "✨ <b>YAXSHI! NORMADA</b> ✨"
        verdict = f"⚡ Tejash: <b>{fmt_duration_sec(saved)}</b>"
        return banner, verdict, progress_bar(pct, positive=True)

    waste = work_sec - norm_sec
    pct = min(100.0, waste / max(work_sec, 1) * 100)
    if waste >= norm_sec:
        banner = "🚨 <b>DIQQAT! JIDDIY KECHIKISH</b> 🚨"
    else:
        banner = "⚠️ <b>NORMADAN SEKIN</b> ⚠️"
    verdict = f"❌ Ortiqcha vaqt: <b>{fmt_duration_sec(waste)}</b>"
    return banner, verdict, progress_bar(pct, positive=False)


def finish_report(
    *,
    name: str,
    started_at: str,
    ended_at: str,
    poz: int,
    work_sec: int,
    norm_sec_per_poz: int,
    photo_count: int,
    points: int,
    hub_synced: bool = True,
    hub_via: str = "",
) -> str:
    norm_total = poz * norm_sec_per_poz
    banner, verdict, bar = _finish_banner(
        poz=poz, work_sec=work_sec, norm_sec=norm_total, points=points
    )
    date_str = started_at[:10] if started_at else "—"
    t0 = fmt_hm(started_at)
    t1 = fmt_hm(ended_at) if ended_at else t0

    ball_line = f"🏆 Markirovka: <b>{points}</b> ball"
    if points == poz and poz > 0:
        ball_line += "  <i>(1 poz = 1 ball)</i>"
    elif points < poz:
        ball_line += "  <i>(20 poz = 1 ball)</i>"

    lines = [
        banner,
        "",
        "📊 <b>MARKIROVKA YAKUNLANDI</b>",
        "",
        f"👤 <b>{_he(name)}</b>",
        f"🕐 {date_str}  ·  <b>{t0}</b> → <b>{t1}</b>",
        "",
        _SEP,
        f"📦 <b>{poz}</b> pozitsiya",
        f"📷 <b>{photo_count}</b> ta rasm",
    ]
    if verdict:
        lines.append(verdict)
    lines.append(ball_line)
    lines.append(bar)
    if hub_synced:
        hub_line = "✅ Hisobot <b>Маркеровка</b> qatoriga yuborildi"
        if hub_via:
            hub_line += f"  <i>({html.escape(hub_via)})</i>"
    else:
        hub_line = (
            "⚠️ <b>Маркеровка</b> qatoriga yuborilmadi — admin ga xabar bering.\n"
            "<i>(YORDAMCHI_HUB_SECRET tekshirilsin)</i>"
        )
    lines.extend(
        [
            "",
            _SEP,
            f"⏱ Ish vaqti: <b>{fmt_duration_sec(work_sec)}</b>",
            f"📐 Norma: <b>{fmt_duration_sec(norm_total)}</b>  "
            f"<i>({norm_sec_per_poz} sek/poz)</i>",
            "",
            hub_line,
        ]
    )
    return "\n".join(lines)
