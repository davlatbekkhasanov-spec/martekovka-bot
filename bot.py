"""Markirovka — vaqt + miqdor + rasm, hub → Маркеровка."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BotCommand, KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from employee_registry import TG_EMPLOYEE, operator_display_name
from hub_summary import daily_summary, fmt_clock
from persist_data import bootstrap_persistence, persistence_status_line, resolve_db_path
from storage import (
    NORM_SEC_PER_POZ,
    add_session_photo,
    calc_points,
    cancel_open,
    complete_session,
    get_open_session,
    init_db,
    live_work_seconds,
    mark_hub_pushed,
    request_finish,
    set_poz_await_photos,
    start_session,
    done_sessions_for_day,
    today_done_sessions,
    today_stats,
    unpushed_done_days,
)
from notify import (
    finish_report,
    group_finished_message,
    group_started_message,
    send_group,
)
from telegram_polling_guard import ensure_polling_mode
from yordamchi_push import (
    hub_configured,
    hub_status_line,
    push_session_end_background,
    push_session_start_background,
    push_to_yordamchi_hub,
    push_to_yordamchi_hub_background,
    today_iso,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "1432810519").strip()
GROUP_ID_RAW = os.getenv("GROUP_ID", "-1001877019294").strip()
TZ = ZoneInfo(os.getenv("TZ", "Asia/Tashkent"))

_DB_BOOT = bootstrap_persistence(
    resolve_db_path(default_filename="martekovka.db"),
    legacy_names=("martekovka.db",),
)
DB_PATH = _DB_BOOT["db_path"]
GROUP_ID = int(GROUP_ID_RAW) if GROUP_ID_RAW.lstrip("-").isdigit() else 0

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN kerak (Railway Variables).")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("martekovka-bot")

BTN_START = "Boshlash"
BTN_FINISH = "Tugatish"
BTN_DONE = "Yakunlash"
BTN_TODAY = "Bugun"
BTN_CANCEL = "Bekor"

rt = Router()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(rt)


def _parse_admin_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for part in re.split(r"[,\s]+", raw.strip()):
        if part.isdigit():
            out.add(int(part))
    return out


ADMIN_IDS = _parse_admin_ids(ADMIN_IDS_RAW)


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


def is_worker(uid: int) -> bool:
    return int(uid) in TG_EMPLOYEE


def can_use_bot(uid: int) -> bool:
    return is_worker(uid) or is_admin(uid)


def user_display_name(uid: int) -> str:
    if is_admin(uid) and not is_worker(uid):
        return "Admin"
    return operator_display_name(uid)


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_START), KeyboardButton(text=BTN_TODAY)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Tugmani bosing...",
    )


def active_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_FINISH)],
            [KeyboardButton(text=BTN_TODAY)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Ish vaqti ketmoqda...",
    )


def qty_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Pozitsiya sonini yozing...",
    )


def photo_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_DONE)],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Rasm yuboring...",
    )


def kb_for_session(ws) -> ReplyKeyboardMarkup:
    if ws.status == "active":
        return active_kb()
    if ws.status == "awaiting_qty":
        return qty_kb()
    if ws.status == "awaiting_photos":
        return photo_kb()
    return main_kb()


async def deny_if_not_allowed(m: Message) -> bool:
    if not m.from_user:
        return True
    uid = m.from_user.id
    if can_use_bot(uid):
        return False
    await m.answer(
        "❌ Bu bot faqat ruxsat berilgan xodimlar uchun.\n"
        f"Sizning Telegram ID: <code>{uid}</code>",
        reply_markup=ReplyKeyboardRemove(),
    )
    return True


async def sync_day_hub(tg_id: int, day: str | None = None) -> tuple[bool, str]:
    day_iso = (day or today_iso())[:10]
    sessions = done_sessions_for_day(DB_PATH, tg_id, day_iso)
    if not sessions:
        return False, "sessiya yo'q"
    summary = daily_summary(sessions)
    if not re.search(r"poz\s*[1-9]", summary.lower()):
        return False, "poz 0"
    ok, via = await push_to_yordamchi_hub(tg_id=tg_id, summary=summary, day_iso=day_iso)
    if ok:
        for s in sessions:
            mark_hub_pushed(DB_PATH, s.id)
        log.info("Hub sync uid=%s day=%s via=%s %s", tg_id, day_iso, via, summary[:80])
    else:
        log.warning(
            "Hub sync failed uid=%s day=%s via=%s summary=%s",
            tg_id,
            day_iso,
            via,
            summary[:80],
        )
        push_to_yordamchi_hub_background(tg_id=tg_id, summary=summary, day_iso=day_iso)
    return ok, via


def _status_text(ws) -> str:
    work = live_work_seconds(ws)
    norm = ws.poz * NORM_SEC_PER_POZ if ws.poz else 0
    labels = {
        "active": "▶️ ishlayapti",
        "awaiting_qty": "🔢 pozitsiya kutilmoqda",
        "awaiting_photos": "📷 rasm kutilmoqda",
    }
    lines = [
        "<b>Markirovka</b>",
        f"Holat: {labels.get(ws.status, ws.status)}",
        f"Ish vaqti: <b>{fmt_clock(work)}</b>",
        f"Norm: <b>{NORM_SEC_PER_POZ} sek/poz</b>",
    ]
    if ws.poz:
        lines.append(f"Pozitsiya: <b>{ws.poz}</b>")
        lines.append(f"Norm vaqt: <b>{fmt_clock(norm)}</b>")
    if ws.status == "awaiting_photos":
        lines.append(f"Rasmlar: <b>{ws.photo_count}</b> ta")
    return "\n".join(lines)


async def set_commands() -> None:
    cmds = [
        BotCommand(command="start", description="Botni ochish"),
        BotCommand(command="whoami", description="ID tekshirish"),
    ]
    try:
        await bot.set_my_commands(cmds)
    except Exception as e:
        log.warning("set_my_commands: %s", e)


@rt.message(Command("start"))
async def cmd_start(m: Message) -> None:
    if not m.from_user:
        return
    uid = m.from_user.id
    if not can_use_bot(uid):
        return await m.answer(
            "❌ Siz ro'yxatda yo'qsiz.\n"
            f"Telegram ID: <code>{uid}</code>",
            reply_markup=ReplyKeyboardRemove(),
        )

    ws = get_open_session(DB_PATH, uid)
    if ws:
        if ws.status == "awaiting_qty":
            return await m.answer(
                "🔢 Nechta pozitsiya (markirovka) qildingiz?\nFaqat raqam yuboring.",
                reply_markup=qty_kb(),
            )
        if ws.status == "awaiting_photos":
            return await m.answer(
                f"📷 Markirovka qilingan tovarlar <b>rasmini</b> yuboring.\n"
                f"Hozir: <b>{ws.photo_count}</b> ta rasm.\n"
                f"Tugatish uchun <b>{BTN_DONE}</b> bosing.",
                reply_markup=photo_kb(),
            )
        return await m.answer(_status_text(ws), reply_markup=kb_for_session(ws))

    await m.answer(
        f"Assalomu alaykum, <b>{user_display_name(uid)}</b>! 👋\n\n"
        f"• <b>{BTN_START}</b> — ish vaqti (norm: {NORM_SEC_PER_POZ} sek/poz)\n"
        f"• <b>{BTN_FINISH}</b> — pozitsiya + rasm\n"
        f"• Norm ichida: 1 poz = 1 ball\n"
        f"• Kechiksa: 20 poz = 1 ball\n\n"
        "Natija yordamchi botda <b>Маркеровка</b> qatoriga tushadi.",
        reply_markup=main_kb(),
    )


@rt.message(F.text == BTN_START)
async def on_start_work(m: Message) -> None:
    if await deny_if_not_allowed(m):
        return
    uid = m.from_user.id
    if get_open_session(DB_PATH, uid):
        return await cmd_start(m)

    ws = start_session(DB_PATH, uid)
    push_session_start_background(tg_id=uid, user_name=user_display_name(uid))
    await send_group(bot, GROUP_ID, group_started_message(name=user_display_name(uid)))
    await m.answer(
        "▶️ <b>Ish boshlandi!</b>\n\n" + _status_text(ws),
        reply_markup=active_kb(),
    )


@rt.message(F.text == BTN_FINISH)
async def on_finish(m: Message) -> None:
    if await deny_if_not_allowed(m):
        return
    uid = m.from_user.id
    ws = get_open_session(DB_PATH, uid)
    if not ws or ws.status != "active":
        return await m.answer("⚠️ Faol sessiya yo'q.", reply_markup=main_kb())

    ws = request_finish(DB_PATH, uid)
    if not ws:
        return await m.answer("⚠️ Sessiya topilmadi.", reply_markup=main_kb())
    push_session_end_background(tg_id=uid)
    await m.answer(
        "🏁 <b>Tugatish</b>\n\n"
        "Nechta pozitsiya markirovka qildingiz?\n"
        "Faqat raqam yuboring (masalan: <code>108</code>).",
        reply_markup=qty_kb(),
    )


@rt.message(F.text == BTN_DONE)
async def on_done_photos(m: Message) -> None:
    if await deny_if_not_allowed(m):
        return
    uid = m.from_user.id
    ws = get_open_session(DB_PATH, uid)
    if not ws or ws.status != "awaiting_photos":
        return await m.answer("⚠️ Rasm bosqichi faol emas.", reply_markup=main_kb())
    if ws.photo_count < 1:
        return await m.answer(
            "⚠️ Kamida 1 ta rasm yuboring, keyin Yakunlash bosing.",
            reply_markup=photo_kb(),
        )

    done = complete_session(DB_PATH, uid)
    if not done:
        return await m.answer("⚠️ Sessiyani yakunlab bo'lmadi.", reply_markup=photo_kb())

    pts = calc_points(done.poz, done.work_sec)
    hub_ok, hub_via = await sync_day_hub(uid)

    name = user_display_name(uid)
    report = finish_report(
        name=name,
        started_at=done.started_at,
        ended_at=done.ended_at or "",
        poz=done.poz,
        work_sec=done.work_sec,
        norm_sec_per_poz=NORM_SEC_PER_POZ,
        photo_count=done.photo_count,
        points=pts,
        hub_synced=hub_ok,
        hub_via=hub_via,
    )
    await send_group(
        bot,
        GROUP_ID,
        group_finished_message(
            name=name,
            poz=done.poz,
            points=pts,
            photos=done.photo_count,
            work_sec=done.work_sec,
        ),
    )
    await m.answer(report, reply_markup=main_kb())


@rt.message(F.text == BTN_CANCEL)
async def on_cancel(m: Message) -> None:
    if await deny_if_not_allowed(m):
        return
    uid = m.from_user.id
    ws = get_open_session(DB_PATH, uid)
    if not ws:
        return await m.answer("Bekor qilinadigan sessiya yo'q.", reply_markup=main_kb())
    if ws.status in ("awaiting_qty", "awaiting_photos"):
        cancel_open(DB_PATH, uid)
        push_session_end_background(tg_id=uid)
        return await m.answer("❌ Sessiya bekor qilindi.", reply_markup=main_kb())
    await m.answer("Faqat miqdor/rasm bosqichida bekor qilish mumkin.", reply_markup=kb_for_session(ws))


@rt.message(F.text == BTN_TODAY)
async def on_today(m: Message) -> None:
    if await deny_if_not_allowed(m):
        return
    uid = m.from_user.id
    n, poz, sec, pts = today_stats(DB_PATH, uid)
    open_ws = get_open_session(DB_PATH, uid)
    extra = f"\n\n⚠️ Ochiq sessiya: {open_ws.status}" if open_ws else ""
    await m.answer(
        f"📊 <b>Bugun — {user_display_name(uid)}</b>\n"
        f"Sessiyalar: <b>{n}</b>\n"
        f"Pozitsiya: <b>{poz}</b>\n"
        f"Ish vaqti: <b>{fmt_clock(sec)}</b>\n"
        f"Ball: <b>{pts}</b>{extra}",
        reply_markup=kb_for_session(open_ws) if open_ws else main_kb(),
    )


@rt.message(F.text.regexp(r"^\d+$"), F.chat.type == "private")
async def on_quantity(m: Message) -> None:
    if await deny_if_not_allowed(m):
        return
    uid = m.from_user.id
    ws = get_open_session(DB_PATH, uid)
    if not ws or ws.status != "awaiting_qty":
        return

    poz = int((m.text or "0").strip())
    if poz <= 0 or poz > 9999:
        return await m.answer("⚠️ 1 dan 9999 gacha raqam kiriting.", reply_markup=qty_kb())

    ws = set_poz_await_photos(DB_PATH, uid, poz)
    if not ws:
        return await m.answer("⚠️ Sessiya topilmadi.", reply_markup=main_kb())

    await m.answer(
        f"✅ Pozitsiya: <b>{poz}</b>\n\n"
        "📷 Endi markirovka qilingan tovarlar <b>rasmini</b> yuboring.\n"
        "Rasm soni cheksiz — istalgancha yuboring.\n"
        f"Hammasi tugagach <b>{BTN_DONE}</b> bosing.",
        reply_markup=photo_kb(),
    )


@rt.message(F.photo, F.chat.type == "private")
async def on_photo(m: Message) -> None:
    if await deny_if_not_allowed(m):
        return
    uid = m.from_user.id
    ws = get_open_session(DB_PATH, uid)
    if not ws or ws.status != "awaiting_photos":
        return

    photo = m.photo[-1]
    ws = add_session_photo(DB_PATH, uid, photo.file_id)
    if not ws:
        return

    if GROUP_ID:
        try:
            cap = (
                f"📷 Markirovka rasm\n"
                f"{user_display_name(uid)} · sessiya #{ws.id}\n"
                f"Poz: {ws.poz} · rasm #{ws.photo_count}"
            )
            await bot.send_photo(GROUP_ID, photo.file_id, caption=cap)
        except Exception as e:
            log.warning("Group photo forward: %s", e)

    await m.answer(
        f"📷 Rasm qabul qilindi (<b>{ws.photo_count}</b> ta).\n"
        f"Yana rasm yuboring yoki <b>{BTN_DONE}</b> bosing.",
        reply_markup=photo_kb(),
    )


@rt.message(Command("whoami"))
async def cmd_whoami(m: Message) -> None:
    if not m.from_user:
        return
    uid = m.from_user.id
    await m.answer(
        f"ID: <code>{uid}</code>\n"
        f"Ism: <b>{user_display_name(uid)}</b>\n"
        f"Bot: {'✅' if can_use_bot(uid) else '❌'}",
        reply_markup=main_kb() if can_use_bot(uid) else ReplyKeyboardRemove(),
    )


@rt.message(Command("sync"))
async def cmd_sync(m: Message) -> None:
    if not m.from_user or not is_admin(m.from_user.id):
        return
    if not hub_configured():
        return await m.answer(
            f"❌ Hub sozlanmagan.\n{hub_status_line()}",
            reply_markup=main_kb(),
        )
    args = (m.text or "").strip().split()[1:]
    day = today_iso()
    for a in args:
        if len(a) == 10 and a[4] == "-" and a[7] == "-":
            day = a
            break
    ok_n = skip_n = fail_n = 0
    for tid in TG_EMPLOYEE:
        ok, via = await sync_day_hub(tid, day)
        if ok:
            ok_n += 1
        elif via == "sessiya yo'q":
            skip_n += 1
        else:
            fail_n += 1
    await m.answer(
        f"📅 {day}\n"
        f"✅ Hub sync: {ok_n} muvaffaqiyat, {skip_n} sessiyasiz, {fail_n} xato.\n"
        f"Keyin yordamchi botda: /synccategories {day}",
        reply_markup=main_kb(),
    )


@rt.message(F.chat.type == "private")
async def on_private_fallback(m: Message) -> None:
    if not m.from_user or not can_use_bot(m.from_user.id):
        await deny_if_not_allowed(m)
        return
    ws = get_open_session(DB_PATH, m.from_user.id)
    if ws and ws.status == "awaiting_photos":
        return await m.answer(
            "📷 Faqat rasm yuboring (foto).\n"
            f"Tugatish: <b>{BTN_DONE}</b>",
            reply_markup=photo_kb(),
        )
    if ws and ws.status == "awaiting_qty":
        return await m.answer(
            "🔢 Pozitsiya sonini raqam bilan yuboring.",
            reply_markup=qty_kb(),
        )
    await m.answer("Tugmalardan foydalaning 👇", reply_markup=kb_for_session(ws) if ws else main_kb())


async def startup_hub_backfill() -> None:
    if not hub_configured():
        log.error("YORDAMCHI hub sozlanmagan — %s", hub_status_line())
        return
    days = unpushed_done_days(DB_PATH, limit=14)
    if today_iso() not in days:
        days.insert(0, today_iso())
    seen: set[str] = set()
    for day in days:
        if day in seen:
            continue
        seen.add(day)
        for tid in TG_EMPLOYEE:
            if not done_sessions_for_day(DB_PATH, tid, day):
                continue
            try:
                await sync_day_hub(tid, day)
            except Exception:
                log.exception("startup hub backfill tg=%s day=%s", tid, day)


async def main() -> None:
    log.info(persistence_status_line(DB_PATH))
    init_db(DB_PATH)
    await set_commands()
    await startup_hub_backfill()
    await ensure_polling_mode(bot)
    log.info("Markirovka bot started. Hub: %s", hub_status_line())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
