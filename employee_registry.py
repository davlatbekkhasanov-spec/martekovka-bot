"""Barcha botlar uchun yagona xodim → Telegram ID."""

from __future__ import annotations

import re

PULAT_TG_ID = 7987730795
CANONICAL_PULAT = "Rajabboev Pulat"
SHOXIJAXON_TG_ID = 6706402440
CANONICAL_SHOXIJAXON = "Ibodullaev Shoxijaxon"
OXUNJON_TG_ID = 8663341753

TUVALOV_FARRUX_TG_ID = PULAT_TG_ID
CANONICAL_TUVALOV = CANONICAL_PULAT
OZODBEK_TG_ID = SHOXIJAXON_TG_ID
CANONICAL_OZODBEK = CANONICAL_SHOXIJAXON

TUVALOV_LEGACY_NAMES: frozenset[str] = frozenset(
    {
        "tuvalov farrux",
        "тувалов фаррух",
        "тувалов farrux",
        "фаррух",
        "farrux",
    }
)

PULAT_NAME_KEYS: frozenset[str] = frozenset(
    {
        "rajabboev pulat",
        "rahabboev pulat",
        "ражаббоев пулат",
        "рахаббоев пулат",
        "pulat",
    }
)

OZODBEK_LEGACY_NAMES: frozenset[str] = frozenset(
    {
        "ergashev ozodbek",
        "ozodbek",
        "эргашев",
        "yadullaev umid",
        "yadullaev umidjon",
        "ядуллаев умид",
        "ядуллаев умиджон",
        "umid",
        "umidjon",
    }
)

SHOXIJAXON_NAME_KEYS: frozenset[str] = frozenset(
    {
        "ibodullaev shoxijaxon",
        "ibodullaev shohijaxon",
        "шохижахон",
        "ибодуллаев шохижахон",
        "shoxijaxon",
        "shohijaxon",
    }
)

PULAT_LEGACY_NAMES = PULAT_NAME_KEYS

# Faqat shu Telegram ID lar botdan foydalanadi (boshqa botlar bilan bir xil ro'yxat).
TG_EMPLOYEE: dict[int, str] = {
    SHOXIJAXON_TG_ID: CANONICAL_SHOXIJAXON,
    OXUNJON_TG_ID: "Ravshanov Oxunjon",
    8547365654: "Ruziboev Sindor",
    6931958983: "Mustafoev Abdullo",
    6991673998: "Sagdullaev Yunus",
    5465963344: "Shernazarov Tolib",
    6001619806: "Samadov Tulqin",
    5732350707: "Toxirov Muslimbek",
    8440127425: "Ravshanov Ziyodullo",
    PULAT_TG_ID: CANONICAL_PULAT,
}

EMPLOYEE_NAME_ALIASES: dict[str, int] = {
    CANONICAL_SHOXIJAXON: SHOXIJAXON_TG_ID,
    "Ibodullaev Shohijaxon": SHOXIJAXON_TG_ID,
    "Ergashev Ozodbek": SHOXIJAXON_TG_ID,
    "Ozodbek": SHOXIJAXON_TG_ID,
    "Yadullaev Umidjon": SHOXIJAXON_TG_ID,
    "Yadullaev Umid": SHOXIJAXON_TG_ID,
    "Samadov To'lqin": 6001619806,
    "Samadov Tulqin": 6001619806,
    "Ravshanov Oxunjon": OXUNJON_TG_ID,
    "Oxunjon": OXUNJON_TG_ID,
    "Охунжон": OXUNJON_TG_ID,
    "Ravshanov Ziyodullo": 8440127425,
    "Ravshanov_Z_": 8440127425,
    "Mustafoev Abdullo": 6931958983,
    "Abdullo Mustafoyev": 6931958983,
    "Ruziboev Sindor": 8547365654,
    "Ruziboev sindorbek": 8547365654,
    "Toxirov Muslimbek": 5732350707,
    "Тохиров Муслимбек": 5732350707,
    "Shernazarov Tolib": 5465963344,
    "Толиб Шерназаров": 5465963344,
    "Sagdullaev Yunus": 6991673998,
    "Sagdullaev": 6991673998,
    CANONICAL_PULAT: PULAT_TG_ID,
    "Rahabboev Pulat": PULAT_TG_ID,
    "Ражаббоев Пулат": PULAT_TG_ID,
    "Рахаббоев Пулат": PULAT_TG_ID,
    "Tuvalov Farrux": PULAT_TG_ID,
    "Тувалов Фаррух": PULAT_TG_ID,
    "Тувалов Farrux": PULAT_TG_ID,
}

SHORT_NAME_ALIASES: dict[str, str] = {
    "охунжон": "Ravshanov Oxunjon",
    "oxunjon": "Ravshanov Oxunjon",
    "ravshanov oxunjon": "Ravshanov Oxunjon",
    "ravshanov_z_": "Ravshanov Ziyodullo",
    "ravshanov z": "Ravshanov Ziyodullo",
    "ziyodullo": "Ravshanov Ziyodullo",
    "abdullo mustafoyev": "Mustafoev Abdullo",
    "mustafoyev abdullo": "Mustafoev Abdullo",
    "mustafoev abdullo": "Mustafoev Abdullo",
    "ruziboev sindorbek": "Ruziboev Sindor",
    "sindorbek": "Ruziboev Sindor",
    "тохиров муслимбек": "Toxirov Muslimbek",
    "toxirov muslimbek": "Toxirov Muslimbek",
    "толиб шерназаров": "Shernazarov Tolib",
    "shernazarov tolib": "Shernazarov Tolib",
    "толиб": "Shernazarov Tolib",
    "tolib": "Shernazarov Tolib",
    "samadov tolqin": "Samadov To'lqin",
    "samadov to'lqin": "Samadov To'lqin",
    "to'lqin": "Samadov To'lqin",
    "sagdullaev": "Sagdullaev Yunus",
    "yunus": "Sagdullaev Yunus",
    "shoxijaxon": CANONICAL_SHOXIJAXON,
    "shohijaxon": CANONICAL_SHOXIJAXON,
    "ozodbek": CANONICAL_SHOXIJAXON,
    "эргашев": CANONICAL_SHOXIJAXON,
    "pulat": CANONICAL_PULAT,
    "rajabboev pulat": CANONICAL_PULAT,
    "rahabboev pulat": CANONICAL_PULAT,
    "tuvalov farrux": CANONICAL_PULAT,
    "farrux": CANONICAL_PULAT,
    "тувалов фаррух": CANONICAL_PULAT,
}


def _alias_key(raw: str) -> str:
    s = (raw or "").strip().lower()
    for ch in ("õ", "ö", "ó", "ô", "'", "'", "`", "ʻ", "ʼ", "’"):
        s = s.replace(ch, "o" if ch in ("õ", "ö", "ó", "ô") else "")
    s = re.sub(r"[_]+", " ", s)
    return " ".join(s.split())


def all_team_tg_ids() -> frozenset[int]:
    return frozenset(TG_EMPLOYEE.keys())


def operator_display_name(tg_id: int) -> str:
    return TG_EMPLOYEE.get(int(tg_id), f"ID {tg_id}")
