# -*- coding: utf-8 -*-
"""Пересечение выгрузки GetCourse с нашей прод-базой лидов.

Все ключи — ASCII-слаги из parse_gc_export.py (gc_id, email, phone, vk_id...).
Ключи склейки с нашей базой: email (lower), телефон (нормализация 8/7), VK-ID.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

BASE = Path(r"C:/Users/circlealgorythm/Documents/доки/Projects/Школа AisuKam/tmp/gc-export-20261106")


def norm_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    if len(d) == 11 and d[0] in "78":
        d = "8" + d[1:]
    return d


def main() -> int:
    payload = json.loads((BASE / "users_clean.json").read_text(encoding="utf-8"))
    gc = payload["rows"]

    ours: dict[str, dict] = {}
    for line in (BASE / "our_leads.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split("|")
        if len(parts) < 9:
            continue
        lid, _gcid, source, _status, email, phone, vk, tg, _created = parts[:9]
        rec = ours.setdefault(
            lid, {"email": set(), "phone": set(), "vk": set(), "tg": set(), "sources": set()}
        )
        if email:
            rec["email"].add(email.strip().lower())
        if phone:
            rec["phone"].add(norm_phone(phone))
        if vk:
            rec["vk"].add(vk.strip())
        if tg:
            rec["tg"].add(tg.strip())
        if source:
            rec["sources"].add(source)

    our_emails = {e for r in ours.values() for e in r["email"]}
    our_phones = {p for r in ours.values() for p in r["phone"]}
    our_vks = {v for r in ours.values() for v in r["vk"]}
    print(f"our leads: {len(ours)}, emails: {len(our_emails)}, phones: {len(our_phones)}, vk: {len(our_vks)}")

    gc_by_email: dict[str, list[dict]] = {}
    gc_by_phone: dict[str, list[dict]] = {}
    gc_by_vk: dict[str, list[dict]] = {}
    for u in gc:
        if u.get("email"):
            gc_by_email.setdefault(u["email"].strip().lower(), []).append(u)
        p = norm_phone(u.get("phone", ""))
        if p:
            gc_by_phone.setdefault(p, []).append(u)
        v = (u.get("vk_id") or "").strip()
        if v:
            gc_by_vk.setdefault(v, []).append(u)
    print(
        f"gc users: {len(gc)}, uniq emails: {len(gc_by_email)}, "
        f"uniq phones: {len(gc_by_phone)}, uniq vk: {len(gc_by_vk)}"
    )

    matched, by_email, by_phone, by_vk = set(), set(), set(), set()
    gc_matched_ids: set[str] = set()
    for lid, r in ours.items():
        for e in r["email"]:
            hits = gc_by_email.get(e, [])
            if hits:
                by_email.add(lid)
                matched.add(lid)
                gc_matched_ids.update(u["gc_id"] for u in hits)
        for p in r["phone"]:
            hits = gc_by_phone.get(p, [])
            if hits:
                by_phone.add(lid)
                matched.add(lid)
                gc_matched_ids.update(u["gc_id"] for u in hits)
        for v in r["vk"]:
            hits = gc_by_vk.get(v, [])
            if hits:
                by_vk.add(lid)
                matched.add(lid)
                gc_matched_ids.update(u["gc_id"] for u in hits)

    print()
    print(f"OUR leads matched in GC: {len(matched)} / {len(ours)}")
    print(f"  by email: {len(by_email)}, by phone: {len(by_phone)}, by vk: {len(by_vk)}")
    new_users = [u for u in gc if u["gc_id"] not in gc_matched_ids]
    useful = [u for u in new_users if u.get("email") or u.get("phone")]
    print(f"GC users NEW for our base: {len(new_users)}")
    print(f"  with email or phone: {len(useful)}")

    dup_emails = sum(1 for v in gc_by_email.values() if len(v) > 1)
    dup_phones = sum(1 for v in gc_by_phone.values() if len(v) > 1)
    print()
    print(f"GC internal dups: email shared: {dup_emails}, phone shared: {dup_phones}")

    # распечатать несколько примеров склеек по VK для визуальной проверки
    print("\nSAMPLE vk matches:")
    shown = 0
    for lid, r in ours.items():
        if shown >= 3:
            break
        for v in r["vk"]:
            hits = gc_by_vk.get(v, [])
            if hits:
                u = hits[0]
                print(f"  lead {lid[:8]} vk={v} -> gc_id={u['gc_id']} email={u['email']} phone={u['phone']} name={u['first_name']} {u['last_name']}")
                shown += 1
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
