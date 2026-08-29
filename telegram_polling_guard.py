"""Webhook bo'lsa o'chiradi — faqat polling ishlashi uchun."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


async def ensure_polling_mode(bot, *, drop_pending: bool = True) -> None:
    me = await bot.get_me()
    wh = await bot.get_webhook_info()
    log.info("Telegram bot: @%s (id=%s)", me.username, me.id)
    if wh.url:
        log.warning("Webhook topildi (%s) — o'chirilmoqda", wh.url)
        await bot.delete_webhook(drop_pending_updates=drop_pending)
    else:
        log.info("Webhook yo'q — polling rejimi")
