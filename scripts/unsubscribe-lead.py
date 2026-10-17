#!/usr/bin/env python3
"""
Скрипт ручной отписки лида от email-рассылок (Unisender Go + FunnelHub DB).

Использование:
  python scripts/unsubscribe-lead.py --email user@example.com
  python scripts/unsubscribe-lead.py --lead-id <UUID>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select

from funnelhub.config import get_settings
from funnelhub.db.models import EmailSubscription, Event, FunnelState, Lead, LeadContact
from funnelhub.db.session import async_session_maker


async def suppress_in_unisender_go(api_key: str, email: str) -> dict[str, Any]:
    url_set = "https://goapi.unisender.ru/ru/transactional/api/v1/suppression/set.json"
    url_get = "https://goapi.unisender.ru/ru/transactional/api/v1/suppression/get.json"
    headers = {"Accept": "application/json", "X-API-KEY": api_key}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp_set = await client.post(
            url_set,
            json={"email": email, "cause": "unsubscribed"},
            headers=headers,
        )
        if resp_set.status_code == 200:
            set_data = resp_set.json()
        else:
            set_data = {
                "status": "error",
                "code": resp_set.status_code,
                "text": resp_set.text,
            }

        resp_get = await client.post(url_get, json={"email": email}, headers=headers)
        get_data = resp_get.json() if resp_get.status_code == 200 else {}

    return {"set": set_data, "get": get_data}


async def unsubscribe_lead(*, email: str | None = None, lead_id_str: str | None = None) -> None:
    settings = get_settings()
    now = datetime.now(UTC)

    async with async_session_maker() as session:
        target_lead_id: uuid.UUID | None = None
        target_email: str | None = email.strip().lower() if email else None

        if lead_id_str:
            target_lead_id = uuid.UUID(lead_id_str.strip())
            lead = await session.get(Lead, target_lead_id)
            if not lead:
                print(f"[-] Лид с ID {target_lead_id} не найден.")
                sys.exit(1)
            if not target_email:
                contact = await session.scalar(
                    select(LeadContact).where(
                        LeadContact.lead_id == target_lead_id,
                        LeadContact.contact_type == "email",
                    )
                )
                if contact:
                    target_email = contact.value.strip().lower()

        if not target_email and not target_lead_id:
            print("[-] Необходимо указать --email или --lead-id.")
            sys.exit(1)

        # Поиск подписок
        sub_query = select(EmailSubscription)
        if target_lead_id:
            sub_query = sub_query.where(EmailSubscription.lead_id == target_lead_id)
        elif target_email:
            sub_query = sub_query.where(EmailSubscription.normalized_email == target_email)

        subscriptions = (await session.scalars(sub_query)).all()

        if not subscriptions and target_email:
            contact = await session.scalar(
                select(LeadContact).where(
                    LeadContact.contact_type == "email",
                    LeadContact.normalized_value == target_email,
                )
            )
            if contact:
                target_lead_id = contact.lead_id

        if not subscriptions and not target_lead_id:
            print(f"[-] Подписок или лида для {target_email or target_lead_id} не найдено.")
            sys.exit(1)

        print(f"[+] Отписка лида: target_email={target_email}, lead_id={target_lead_id}")

        # 1. Обновление EmailSubscription
        unsubscribed_subs = 0
        for sub in subscriptions:
            target_lead_id = target_lead_id or sub.lead_id
            target_email = target_email or sub.email
            was_subscribed = sub.status != "unsubscribed"
            sub.status = "unsubscribed"
            sub.unsubscribed_at = sub.unsubscribed_at or now
            unsubscribed_subs += 1

            if was_subscribed:
                event = Event(
                    id=uuid.uuid4(),
                    lead_id=sub.lead_id,
                    event_type="email.unsubscribed",
                    source="manual_admin",
                    occurred_at=now,
                    payload={
                        "email_subscription_id": str(sub.id),
                        "email": sub.email,
                        "reason": "user_requested_unsubscribe_manual",
                    },
                    dedupe_key=f"email.unsubscribed:{sub.id}:manual",
                )
                session.add(event)

        print(f"[OK] Обновлено записей EmailSubscription: {unsubscribed_subs}")

        # 2. Остановка активных email FunnelState
        paused_funnels = 0
        if target_lead_id:
            f_states = (await session.scalars(
                select(FunnelState).where(
                    FunnelState.lead_id == target_lead_id,
                    FunnelState.channel == "email",
                )
            )).all()

            for fs in f_states:
                if fs.status == "active":
                    fs.status = "paused"
                    fs.paused_at = now
                    fs.next_run_at = None
                    fs.metadata_ = {
                        **(fs.metadata_ or {}),
                        "paused_reason": "user_requested_unsubscribe",
                        "unsubscribed_at": now.isoformat(),
                    }
                    paused_funnels += 1

        print(f"[OK] Приостановлено активных воронок (channel=email): {paused_funnels}")

        await session.commit()

        # 3. Unisender Go suppression
        if target_email and settings.email_unisender_go_api_key:
            print(f"[+] Добавление {target_email} в Unisender Go suppression list...")
            res = await suppress_in_unisender_go(settings.email_unisender_go_api_key, target_email)
            print(f"[OK] Unisender Go suppression result: {res}")
        else:
            print("[!] Пропуск Unisender Go (нет api_key или email).")

        print("[УСПЕХ] Лид успешно отписан от рассылок.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ручная отписка лида от email-рассылок.")
    parser.add_argument("--email", help="Email адрес лида")
    parser.add_argument("--lead-id", help="UUID лида")
    args = parser.parse_args()

    if not args.email and not args.lead_id:
        parser.print_help()
        sys.exit(1)

    asyncio.run(unsubscribe_lead(email=args.email, lead_id_str=args.lead_id))


if __name__ == "__main__":
    main()
