"""Martekovka / markerovka — vaqt + miqdor, hub → Фасовка."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from employee_registry import TG_EMPLOYEE, operator_display_name
from hub_summary import daily_summary, fmt_clock, session_summary
from persist_data import bootstrap_persistence, persistence_status_line, resolve_db_path
from storage import (
    cancel_open,
    complete_finish,
    get_open_session,
    init_db,
    live_work_seconds,
    pause_session,
    request_finish,
    resume_session,
    start_session,
    today_done_sessions,
    today_stats,
)
from telegram_polling_guard import ensure_polling_mode
from yordamchi_push import (
    push_session_end_background,
    push_session_start_background,
    push_to_yordamchi_hub,
    push_to_yordamchi_hub_background,
    today_iso,
)
from storage import mark_hub_pushed

# ===================== CONFIG =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "1432810519").strip()
TZ = ZoneInfo(os.getenv("TZ", "Asia/Tashkent"))

_DB_BOOT = bootstrap_persistence(
    resolve_db_path(default_filename="martekovka.db"),
    legacy_names=("martekovka.db",),
)
DB_PATH = _DB_BOOT["db_path"]


def _parse_admin_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for part in re.split(r"[,\s]+", raw.strip()):
        if part.isdigit():
            out.add(int(part))
    return out


ADMIN_IDS = _parse_admin_ids(ADMIN_IDS_RAW)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN kerak (Railway Variables).")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("martekovka-bot")

BTN_START = "▶️ Boshlash"
BTN_PAUSE = "⏸ Tanaffus"
BTN_RESUME = "▶️ Davom etish"
BTN_FINISH = "✔️ Tugatish"
BTN_TODAY = "📊 Bugun"
BTN_CANCEL = "❌ Bekor qilish"

rt = Router()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(rt)


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


def is_worker(uid: int) -> bool:
    return int(uid) in TG_EMPLOYEE


def idle_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_START), KeyboardButton(text=BTN_TODAY)]],
        resize_keyboard=True,
    )


def active_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PAUSE), KeyboardButton(text=BTN_FINISH)],
            [KeyboardButton(text=BTN_TODAY)],
        ],
        resize_keyboard=True,
    )


def paused_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_RESUME), KeyboardButton(text=BTN_FINISH)],
            [KeyboardButton(text=BTN_TODAY)],
        ],
        resize_keyboard=True,
    )


def awaiting_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


async def sync_day_hub(tg_id: int, day: str | None = None) -> None:
    day_iso = day or today_iso()
    sessions = today_done_sessions(DB_PATH, tg_id)
    summary = daily_summary(sessions)
    ok, via = await push_to_yordamchi_hub(tg_id=tg_id, summary=summary, day_iso=day_iso)
    if ok:
        log.info("Hub sync uid=%s via=%s %s", tg_id, via, summary[:80])
    else:
        log.warning("Hub sync failed uid=%s via=%s", tg_id, via)
        push_to_yordamchi_hub_background(tg_id=tg_id, summary=summary, day_iso=day_iso)


def _status_text(ws) -> str:
    ish = fmt_clock(live_work_seconds(ws))
    dam = fmt_clock(ws.pause_sec)
    st = {"active": "▶️ ishlayapti", "paused": "⏸ pauzada", "awaiting_qty": "🏁 miqdor kutilmoqda"}.get(
        ws.status, ws.status
    )
    return (
        f"<b>Martekovka sessiyasi</b>\n"
        f"Holat: {st}\n"
        f"Ish vaqti: <b>{ish}</b>\n"
        f"Tanaffus: <b>{dam}</b>\n"
        f"Boshlangan: <code>{ws.started_at}</code>"
    )


@rt.message(Command("start"))
async def cmd_start(m: Message) -> None:
    if not m.from_user:
        return
    uid = m.from_user.id
    if not is_worker(uid) and not is_admin(uid):
        return await m.answer(
            "❌ Siz ro'yxatda yo'qsiz.\n"
            f"Telegram ID: <code>{uid}</code>\n"
            "Rahbariyatga murojaat qiling."
        )

    ws = get_open_session(DB_PATH, uid)
    if ws:
        kb = paused_kb() if ws.status == "paused" else active_kb()
        if ws.status == "awaiting_qty":
            kb = awaiting_kb()
            return await m.answer(
                "🏁 <b>Yakunlash davom etmoqda</b>\n\nNechta pozitsiya (markirovka) qildingiz?\nFaqat raqam yuboring.",
                reply_markup=kb,
            )
        return await m.answer(_status_text(ws), reply_markup=kb)

    name = operator_display_name(uid)
    await m.answer(
        f"Assalomu alaykum, <b>{name}</b>! 👋\n\n"
        "Martekovka vaqt + miqdor boti.\n"
        "▶️ <b>Boshlash</b> — ish vaqtini hisoblash\n"
        "✔️ <b>Tugatish</b> — pozitsiya sonini kiritish\n\n"
        "Bugungi natija avtomatik yordamchi hisobotiga (Фасовка) tushadi.",
        reply_markup=idle_kb(),
    )


@rt.message(F.text == BTN_START)
async def on_start(m: Message) -> None:
    if not m.from_user or not is_worker(m.from_user.id):
        return await m.answer("Ruxsat yo'q.")
    uid = m.from_user.id
    if get_open_session(DB_PATH, uid):
        return await cmd_start(m)

    ws = start_session(DB_PATH, uid)
    name = operator_display_name(uid)
    push_session_start_background(tg_id=uid, user_name=name)
    await m.answer(
        "▶️ <b>Ish boshlandi!</b>\n\n" + _status_text(ws),
        reply_markup=active_kb(),
    )


@rt.message(F.text == BTN_PAUSE)
async def on_pause(m: Message) -> None:
    if not m.from_user or not is_worker(m.from_user.id):
        return
    ws = pause_session(DB_PATH, m.from_user.id)
    if not ws:
        return await m.answer("⚠️ Faol sessiya yo'q yoki allaqachon pauzada.", reply_markup=idle_kb())
    await m.answer("⏸ <b>Tanaffus</b>\n\n" + _status_text(ws), reply_markup=paused_kb())


@rt.message(F.text == BTN_RESUME)
async def on_resume(m: Message) -> None:
    if not m.from_user or not is_worker(m.from_user.id):
        return
    ws = resume_session(DB_PATH, m.from_user.id)
    if not ws:
        return await m.answer("⚠️ Pauzada sessiya yo'q.", reply_markup=idle_kb())
    await m.answer("▶️ <b>Davom etildi</b>\n\n" + _status_text(ws), reply_markup=active_kb())


@rt.message(F.text == BTN_FINISH)
async def on_finish(m: Message) -> None:
    if not m.from_user or not is_worker(m.from_user.id):
        return
    uid = m.from_user.id
    ws = request_finish(DB_PATH, uid)
    if not ws:
        return await m.answer("⚠️ Faol sessiya yo'q.", reply_markup=idle_kb())
    push_session_end_background(tg_id=uid)
    await m.answer(
        "🏁 <b>Yakunlash</b>\n\n"
        "Nechta pozitsiya (markirovka) qildingiz?\n"
        "Faqat raqam yuboring (masalan: <code>108</code>).",
        reply_markup=awaiting_kb(),
    )


@rt.message(F.text == BTN_CANCEL)
async def on_cancel(m: Message) -> None:
    if not m.from_user or not is_worker(m.from_user.id):
        return
    uid = m.from_user.id
    ws = get_open_session(DB_PATH, uid)
    if not ws:
        return await m.answer("Bekor qilinadigan sessiya yo'q.", reply_markup=idle_kb())
    if ws.status == "awaiting_qty":
        cancel_open(DB_PATH, uid)
        push_session_end_background(tg_id=uid)
        return await m.answer("❌ Sessiya bekor qilindi.", reply_markup=idle_kb())
    await m.answer("Faqat miqdor kutilayotganda bekor qilish mumkin.", reply_markup=awaiting_kb())


@rt.message(F.text == BTN_TODAY)
async def on_today(m: Message) -> None:
    if not m.from_user:
        return
    uid = m.from_user.id
    if not is_worker(uid) and not is_admin(uid):
        return
    n, poz, sec = today_stats(DB_PATH, uid)
    open_ws = get_open_session(DB_PATH, uid)
    extra = ""
    if open_ws:
        extra = f"\n\n⚠️ Ochiq sessiya: {open_ws.status}"
    await m.answer(
        f"📊 <b>Bugun — {operator_display_name(uid)}</b>\n"
        f"Sessiyalar: <b>{n}</b>\n"
        f"Jami pozitsiya: <b>{poz}</b>\n"
        f"Ish vaqti: <b>{fmt_clock(sec)}</b>{extra}",
        reply_markup=paused_kb() if open_ws and open_ws.status == "paused"
        else active_kb() if open_ws and open_ws.status == "active"
        else awaiting_kb() if open_ws and open_ws.status == "awaiting_qty"
        else idle_kb(),
    )


@rt.message(F.text.regexp(r"^\d+$"), F.chat.type == "private")
async def on_quantity(m: Message) -> None:
    if not m.from_user or not is_worker(m.from_user.id):
        return
    uid = m.from_user.id
    ws = get_open_session(DB_PATH, uid)
    if not ws or ws.status != "awaiting_qty":
        return

    poz = int((m.text or "0").strip())
    if poz <= 0 or poz > 9999:
        return await m.answer("⚠️ 1 dan 9999 gacha raqam kiriting.")

    done = complete_finish(DB_PATH, uid, poz)
    if not done:
        return await m.answer("⚠️ Sessiya topilmadi.")

    summary = session_summary(done)
    await sync_day_hub(uid)
    mark_hub_pushed(DB_PATH, done.id)

    await m.answer(
        f"✅ <b>Saqlanadi!</b>\n\n"
        f"Pozitsiya: <b>{poz}</b>\n"
        f"Ish vaqti: <b>{fmt_clock(done.work_sec)}</b>\n"
        f"Tanaffus: <b>{fmt_clock(done.pause_sec)}</b>\n\n"
        f"Hub: <code>{summary}</code>",
        reply_markup=idle_kb(),
    )


@rt.message(Command("whoami"))
async def cmd_whoami(m: Message) -> None:
    if not m.from_user:
        return
    uid = m.from_user.id
    await m.answer(
        f"ID: <code>{uid}</code>\n"
        f"Ism: <b>{operator_display_name(uid)}</b>\n"
        f"Xodim: {'✅' if is_worker(uid) else '❌'}\n"
        f"Admin: {'✅' if is_admin(uid) else '❌'}"
    )


@rt.message(Command("sync"))
async def cmd_sync(m: Message) -> None:
    if not m.from_user or not is_admin(m.from_user.id):
        return
    for tid in TG_EMPLOYEE:
        await sync_day_hub(tid)
    await m.answer("✅ Bugungi hub sync bajarildi.")


async def startup_hub_backfill() -> None:
    day = today_iso()
    for tid in TG_EMPLOYEE:
        sessions = today_done_sessions(DB_PATH, tid)
        if sessions:
            try:
                await sync_day_hub(tid, day)
            except Exception:
                log.exception("hub backfill tg=%s", tid)


async def main() -> None:
    log.info(persistence_status_line(DB_PATH))
    init_db(DB_PATH)
    await startup_hub_backfill()
    await ensure_polling_mode(bot)
    log.info("Martekovka bot started.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
