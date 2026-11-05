# ruff: noqa: E402
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Adjust import path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(env_file, override=True)

from funnelhub.config import get_settings
from funnelhub.db.models import (
    BotLinkToken,
    Conversation,
    Lead,
    LeadContact,
    LeadCustomField,
    LeadTag,
    LeadUtm,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MSK_TZ = timezone(timedelta(hours=3))


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    return digits or None


def parse_datetime_msk(raw: str) -> datetime:
    raw = raw.strip()
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%d.%m.%Y %H:%M:%S")
        except ValueError:
            dt = datetime.fromisoformat(raw)
    return dt.replace(tzinfo=MSK_TZ).astimezone(UTC)


async def run_crm_import(csv_path: Path, dry_run: bool = True) -> None:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(csv_path, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        rows = list(reader)

    print("\n" + "=" * 60)
    print("CRM LEADS RECOVERY AUDIT REPORT")
    print("=" * 60)
    print(f"File path         : {csv_path}")
    print(f"Header columns    : {header}")
    print(f"Total rows in CSV : {len(rows)}")

    stats: dict[str, Any] = {
        "valid_rows": 0,
        "valid_phones": 0,
        "unique_phones": set(),
        "target_leads": 0,
        "spam_leads": 0,
        "other_leads": 0,
        "with_client_id": 0,
    }

    parsed_records = []
    for r in rows:
        if not r or not any(r):
            continue
        date_raw = r[0].strip() if len(r) > 0 else ""
        if not date_raw:
            continue
        name_raw = r[1].strip() if len(r) > 1 else ""
        phone_raw = r[2].strip() if len(r) > 2 else ""
        client_id_raw = r[3].strip() if len(r) > 3 else ""
        status_raw = r[4].strip() if len(r) > 4 else ""

        try:
            dt_utc = parse_datetime_msk(date_raw)
        except Exception as e:
            logger.warning("Failed to parse date '%s': %s", date_raw, e)
            continue

        norm_phone = normalize_phone(phone_raw)
        clean_client_id = "".join(c for c in client_id_raw if c.isdigit())
        if len(clean_client_id) < 16:
            clean_client_id = None

        is_spam = "спам" in status_raw.lower()
        is_target = "таргет" in status_raw.lower()
        if is_spam:
            stats["spam_leads"] += 1
        elif is_target:
            stats["target_leads"] += 1
        else:
            stats["other_leads"] += 1

        if norm_phone:
            stats["valid_phones"] += 1
            stats["unique_phones"].add(norm_phone)

        if clean_client_id:
            stats["with_client_id"] += 1

        stats["valid_rows"] += 1
        parsed_records.append({
            "dt_utc": dt_utc,
            "name_raw": name_raw,
            "phone_raw": phone_raw,
            "norm_phone": norm_phone,
            "client_id": clean_client_id,
            "status_raw": status_raw,
            "is_spam": is_spam,
            "is_target": is_target,
        })

    print(f"Parsed valid rows : {stats['valid_rows']}")
    print(f"Unique phones     : {len(stats['unique_phones'])}")
    print(f"Target leads      : {stats['target_leads']}")
    print(f"Spam leads        : {stats['spam_leads']}")
    print(f"Other leads       : {stats['other_leads']}")
    print(f"With Metrika CID  : {stats['with_client_id']}")
    print("=" * 60)

    if dry_run:
        print("\n[DRY RUN] Audit complete. To apply to PostgreSQL, pass --apply flag.")
        return

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    now_utc = datetime.now(UTC)

    async with AsyncSession(engine) as session:
        created_leads = 0
        updated_leads = 0

        for rec in parsed_records:
            dt_utc = rec["dt_utc"]
            name_raw = rec["name_raw"]
            norm_phone = rec["norm_phone"]
            phone_raw = rec["phone_raw"]
            client_id = rec["client_id"]
            status_raw = rec["status_raw"]
            is_spam = rec["is_spam"]
            is_target = rec["is_target"]

            lead_status = "archived" if is_spam else "active"
            tag = "спам" if is_spam else ("таргет" if is_target else None)

            full_name = name_raw or None
            first_name = None
            last_name = None
            if full_name:
                parts = full_name.split(None, 1)
                first_name = parts[0]
                if len(parts) > 1:
                    last_name = parts[1]

            existing_lead = None
            if norm_phone:
                contact = await session.scalar(
                    select(LeadContact).where(
                        LeadContact.contact_type == "phone",
                        LeadContact.normalized_value == norm_phone,
                    )
                )
                if contact:
                    existing_lead = await session.get(Lead, contact.lead_id)

            if existing_lead:
                if not existing_lead.full_name and full_name:
                    existing_lead.full_name = full_name
                    existing_lead.first_name = first_name
                    existing_lead.last_name = last_name
                updated_leads += 1
            else:
                lead_id = uuid.uuid4()
                lead = Lead(
                    id=lead_id,
                    full_name=full_name,
                    first_name=first_name,
                    last_name=last_name,
                    source="landing_consultation",
                    status=lead_status,
                    created_at=dt_utc,
                    updated_at=dt_utc,
                )
                session.add(lead)
                await session.flush()

                if norm_phone:
                    session.add(
                        LeadContact(
                            id=uuid.uuid4(),
                            lead_id=lead_id,
                            contact_type="phone",
                            value=phone_raw,
                            normalized_value=norm_phone,
                            is_primary=True,
                            is_verified=True,
                            created_at=dt_utc,
                            updated_at=dt_utc,
                        )
                    )

                if client_id:
                    session.add(
                        LeadUtm(
                            id=uuid.uuid4(),
                            lead_id=lead_id,
                            source_kind="form",
                            metrika_client_id=client_id,
                            created_at=dt_utc,
                            updated_at=dt_utc,
                        )
                    )

                if status_raw:
                    session.add(
                        LeadCustomField(
                            id=uuid.uuid4(),
                            lead_id=lead_id,
                            source="crm",
                            field_key="crm_status",
                            field_label="Статус CRM",
                            value=status_raw,
                            created_at=dt_utc,
                            updated_at=dt_utc,
                        )
                    )

                if tag:
                    session.add(
                        LeadTag(
                            id=uuid.uuid4(),
                            lead_id=lead_id,
                            tag=tag,
                            source="crm",
                            created_at=dt_utc,
                            updated_at=dt_utc,
                        )
                    )

                token_val = secrets.token_urlsafe(16)
                session.add(
                    BotLinkToken(
                        id=uuid.uuid4(),
                        lead_id=lead_id,
                        token=token_val,
                        status="active",
                        created_at=dt_utc,
                        updated_at=dt_utc,
                    )
                )

                is_closed = (now_utc - dt_utc).days > 14
                session.add(
                    Conversation(
                        id=uuid.uuid4(),
                        lead_id=lead_id,
                        channel="max",
                        source="landing_consultation",
                        status="closed" if is_closed else "open",
                        last_message_at=dt_utc,
                        created_at=dt_utc,
                        updated_at=dt_utc,
                    )
                )
                await session.flush()
                created_leads += 1

        await session.commit()
        done_msg = (
            f"\n[DONE] Successfully created {created_leads} new leads and "
            f"updated {updated_leads} existing leads in PostgreSQL!"
        )
        print(done_msg)

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Recover CRM leads from Google Sheets CSV export.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=PROJECT_ROOT / "data" / "crm_leads.csv",
        help="Path to CSV file with CRM leads",
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes to PostgreSQL database")
    args = parser.parse_args()

    asyncio.run(run_crm_import(csv_path=args.csv, dry_run=not args.apply))


if __name__ == "__main__":
    main()
