# -*- coding: utf-8 -*-
r"""Парсер выгрузки пользователей GetCourse (export 90643107 + группы 90643875).

ФАКТ (проверено кодпоинтами): JSON API приходит в чистом UTF-8, никакой
перекодировки не нужно. «Mojibake» в консоли — только отрисовка (CP1251-pipe,
отображаемый как CP866). Самопроверка ниже фиксирует эталоны по кодпоинтам.

Элементы items — плоские массивы строк, выровненные по fields позиционно.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SRC = Path(r"C:/Users/circlealgorythm/Documents/доки/Projects/Школа AisuKam/tmp/gc-export-20261106/export_full_90643107.json")
OUT = Path(r"C:/Users/circlealgorythm/Documents/доки/Projects/Школа AisuKam/tmp/gc-export-20261106/users_clean.json")

SLUGS = [
    "gc_id", "email", "reg_type", "created_at", "last_activity",
    "first_name", "last_name", "phone", "birth_date", "age",
    "country", "city", "from_partner",
    "cf_10558670", "cf_10575005", "cf_10616540", "cf_10661024",
    "cf_10682753", "cf_10682754", "cf_10683365", "cf_11344348",
    "sys_utm_source", "sys_utm_medium", "sys_utm_campaign", "sys_utm_term", "sys_utm_content",
    "funnelhub_bot_link", "cf_extra_bool", "came_from",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_group",
    "partner_id", "partner_email", "partner_name", "manager_name", "vk_id",
]


def main() -> int:
    data = json.loads(SRC.read_bytes().decode("utf-8"))
    info = data["info"]
    fields_raw = info["fields"]
    items = info["items"]

    # Позиционная проверка соответствия слагов эталонным значениям строки 0
    row0 = items[0]
    assert row0[0] == "415767714", row0[0]
    assert row0[5] == "\u0410\u0439\u0441\u0443", repr(row0[5])          # Айсу
    assert row0[6] == "\u041a\u0430\u043c", repr(row0[6])                # Кам
    assert row0[10] == "\u0420\u043e\u0441\u0441\u0438\u044f", repr(row0[10])  # Россия

    fields = [f if f else f"(col{i})" for i, f in enumerate(fields_raw)]
    if len(fields) != len(SLUGS):
        print(f"FATAL: fields {len(fields)} != slugs {len(SLUGS)}")
        return 1

    rows = []
    skipped = 0
    for it in items:
        if not (isinstance(it, list) and len(it) == len(SLUGS)):
            skipped += 1
            continue
        rows.append(dict(zip(SLUGS, it)))

    n = len(rows)
    print(f"rows: {n} (skipped: {skipped})")
    print("FILL RATES:")
    for slug in SLUGS:
        filled = sum(1 for r in rows if str(r[slug]).strip() not in ("", "-"))
        if filled:
            print(f"  {slug}: {filled}/{n} ({100 * filled // n}%)")

    OUT.write_text(
        json.dumps({"slugs": SLUGS, "orig_names": fields, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print("saved: users_clean.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
