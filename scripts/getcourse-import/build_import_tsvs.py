# -*- coding: utf-8 -*-
"""Билдер TSV для импорта пользователей GetCourse в FunnelHub.

Вход:  users_clean.json (export 90643107, 40 колонок),
       export_groups2.json (export 90643875, 41 колонка: + группы id:date),
       groups_fixed.json (справочник id → название).
Выход: users.tsv  (стейджинг st_gc, 28 колонок),
       groups.tsv (стейджинг st_groups: gc_id, group_id, added_date).

Конвенции:
- NULL в TSV = \\N
- телефоны: только цифры, RU 11 цифр → префикс 7
- email: технические @vktech.gc → NULL (в подписки/контакты не попадают)
- времена GetCourse интерпретируются как Europe/Moscow (+03, без DST)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

BASE = Path(r"C:/Users/circlealgorythm/Documents/доки/Projects/Школа AisuKam/tmp/gc-export-20261106")

USERS_TSV = BASE / "users.tsv"
GROUPS_TSV = BASE / "groups.tsv"

CF_SLUGS = [
    "cf_10558670",
    "cf_10575005",
    "cf_10616540",
    "cf_10661024",
    "cf_10682753",
    "cf_10682754",
    "cf_10683365",
    "cf_11344348",
    "cf_extra_bool",
]


def fix(s: str) -> str:
    if not isinstance(s, str):
        return s
    try:
        return s.encode("cp866").decode("cp1251")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def norm_phone(p: str) -> str | None:
    d = re.sub(r"\D", "", p or "")
    if not d:
        return None
    if len(d) == 11 and d[0] == "8":
        d = "7" + d[1:]
    if len(d) == 10:
        d = "7" + d
    return d or None


def is_technical_email(e: str) -> bool:
    return e.strip().lower().endswith("@vktech.gc")


def ts_msk(v: str) -> str | None:
    v = (v or "").strip()
    if not v:
        return None
    return v + "+03"


def clean(v: str) -> str:
    """Убрать управляющие символы, ломающие COPY TEXT."""
    return (v or "").replace("\\", "\\\\").replace("\t", " ").replace("\n", " ").replace("\r", " ").strip()


def tsv(v: str | None) -> str:
    return "\\N" if v in (None, "") else v


def main() -> int:
    users = json.loads((BASE / "users_clean.json").read_text(encoding="utf-8"))["rows"]
    gp = json.loads((BASE / "export_groups2.json").read_text(encoding="utf-8"))["info"]
    # имена групп приходят чистым UTF-8 — без перекодировок
    groups_ref = {str(g["id"]): (g.get("name") or "").strip() for g in json.loads((BASE / "groups_fixed.json").read_text(encoding="utf-8"))}

    # группы: слитый по gc_id словарь (export 41 колонка, позиция 40)
    group_rows: dict[str, set[tuple[str, str]]] = {}
    for r in gp["items"]:
        gc_id = r[0]
        raw = fix(r[40]) if len(r) > 40 else ""
        if not raw or raw == "-":
            continue
        for part in raw.split(","):
            if ":" not in part:
                continue
            gid, _, date = part.partition(":")
            gid = gid.strip()
            if gid.isdigit():
                group_rows.setdefault(gc_id, set()).add((gid, date.strip()))

    seen = 0
    with USERS_TSV.open("w", encoding="utf-8", newline="") as fu, GROUPS_TSV.open("w", encoding="utf-8", newline="") as fg:
        for u in users:
            gc_id = u["gc_id"]
            # users_clean.json уже декодирован (fix применён в parse_gc_export) — не чиним второй раз
            email = None if is_technical_email(u.get("email", "")) else clean(u.get("email"))
            phone = norm_phone(u.get("phone", ""))
            vals = [
                gc_id,
                tsv(email),
                tsv(phone),
                tsv(clean(u.get("first_name"))),
                tsv(clean(u.get("last_name"))),
                tsv(clean(u.get("country"))),
                tsv(clean(u.get("city"))),
                tsv(clean(u.get("reg_type"))),
                tsv(ts_msk(u.get("created_at"))),
                tsv(ts_msk(u.get("last_activity"))),
                tsv(clean(u.get("came_from"))),
                tsv(clean(u.get("utm_source"))),
                tsv(clean(u.get("utm_medium"))),
                tsv(clean(u.get("utm_campaign"))),
                tsv(clean(u.get("utm_term"))),
                tsv(clean(u.get("utm_content"))),
                tsv(clean(u.get("vk_id"))),
            ]
            vals += [tsv(clean(u.get(slug))) for slug in CF_SLUGS]
            fu.write("\t".join(vals) + "\n")
            seen += 1
            for gid, date in sorted(group_rows.get(gc_id, set())):
                name = clean(groups_ref.get(gid, ""))
                fg.write(f"{gc_id}\t{gid}\t{tsv(date) if date else chr(92) + 'N'}\t{tsv(name)}\n")

    print(f"users.tsv rows: {seen}")
    print(f"groups.tsv rows: {sum(1 for _ in GROUPS_TSV.open(encoding='utf-8'))}")
    print(f"group names known: {len(groups_ref)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
