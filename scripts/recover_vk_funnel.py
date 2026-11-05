# ruff: noqa: E402
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
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
    Conversation,
    FunnelState,
    Lead,
    MessengerIdentity,
)
from funnelhub.services.funnel_engine import (
    CALENDAR_DAY_OFFSET_METADATA_KEY,
    FUNNEL_STARTED_AT_METADATA_KEY,
    FunnelDefinition,
    build_state_metadata,
    load_funnel_definition,
    parse_delay,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def vk_api_call(
    method: str,
    params: dict[str, Any],
    token: str,
    version: str = "5.199",
) -> dict[str, Any]:
    url = f"https://api.vk.com/method/{method}"
    data = {**params, "access_token": token, "v": version}
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if "error" in result:
        raise RuntimeError(f"VK API Error: {result['error']}")
    return result.get("response", {})


def fetch_all_vk_conversations(token: str, max_count: int = 1000) -> list[dict[str, Any]]:
    conversations: list[dict[str, Any]] = []
    offset = 0
    count_per_req = 200

    logger.info("Starting VK conversations fetch...")
    while True:
        resp = vk_api_call(
            "messages.getConversations",
            {"offset": offset, "count": count_per_req, "extended": 1},
            token=token,
        )
        items = resp.get("items", [])
        if not items:
            break
        conversations.extend(items)
        offset += len(items)
        logger.info(f"Fetched {len(conversations)}/{resp.get('count', '?')} conversations...")
        if len(items) < count_per_req or len(conversations) >= max_count:
            break
        time.sleep(0.35)

    return conversations


def fetch_last_bot_message(peer_id: int, token: str) -> dict[str, Any] | None:
    time.sleep(0.35)
    resp = vk_api_call("messages.getHistory", {"peer_id": peer_id, "count": 20}, token=token)
    for msg in resp.get("items", []):
        if msg.get("out") == 1:
            return msg
    return None


class StepMatcher:
    def __init__(self, definition: FunnelDefinition):
        self.definition = definition
        self.signatures: list[tuple[str, str, int]] = []
        for idx, step in enumerate(definition.steps):
            clean_text = " ".join(step.text.split())
            prefix = clean_text[:60].lower()
            self.signatures.append((step.key, prefix, idx))

        if definition.questionnaire:
            for q_key, q in definition.questionnaire.questions.items():
                clean_text = " ".join(q.text.split())
                prefix = clean_text[:60].lower()
                self.signatures.append((f"q_{q_key}", prefix, 1))

    def match(self, text: str) -> tuple[str | None, int | None]:
        clean_text = " ".join(text.split()).lower()

        # 1. Check for promotional broadcasts (sent to completed funnel users)
        if "осталось всего 5 мест" in clean_text or "шаманская кукла" in clean_text:
            return "broadcast_completed", len(self.definition.steps) - 1

        # 2. Check for manual consultation/operator message
        if "жду ваши данные" in clean_text or "личные сообщения" in clean_text:
            return "manual_consultation", len(self.definition.steps) - 1

        # 3. Direct matching by prefix
        for key, prefix, idx in self.signatures:
            if prefix in clean_text or clean_text[:len(prefix)] == prefix:
                return key, idx

        # 4. Partial matching by keywords
        for key, prefix, idx in self.signatures:
            keywords = [w for w in prefix.split()[:5] if len(w) > 4]
            if len(keywords) >= 3 and all(kw in clean_text for kw in keywords):
                return key, idx

        return None, None


async def run_recovery(dry_run: bool = True):
    settings = get_settings()
    token = settings.vk_group_access_token
    if not token:
        logger.error("VK_GROUP_ACCESS_TOKEN is missing in settings!")
        return

    definition = load_funnel_definition(PROJECT_ROOT / settings.default_funnel_path)
    matcher = StepMatcher(definition)
    total_steps = len(definition.steps)

    conversations = fetch_all_vk_conversations(token)
    logger.info(f"Total conversations retrieved: {len(conversations)}")

    stats = {
        "total": len(conversations),
        "skipped_chats": 0,
        "matched_steps": 0,
        "active_to_resume": 0,
        "completed": 0,
        "unmatched": 0,
    }
    step_distribution: dict[str, int] = {}
    records_to_insert: list[dict[str, Any]] = []

    now = datetime.now(UTC)

    for item in conversations:
        conv = item.get("conversation", {})
        last_msg = item.get("last_message", {})
        peer_id = conv.get("peer", {}).get("id")

        if not peer_id or peer_id < 0:
            stats["skipped_chats"] += 1
            continue

        bot_msg = last_msg if last_msg.get("out") == 1 else fetch_last_bot_message(peer_id, token)
        msg_date_ts = (bot_msg or last_msg).get("date", int(time.time()))
        msg_date = datetime.fromtimestamp(msg_date_ts, tz=UTC)
        age_days = (now - msg_date).total_seconds() / 86400.0

        if not bot_msg:
            # User sent a message, but bot never responded or user opted out
            matched_key = "user_inbound_only"
            step_idx = 0
            status = "completed"
        else:
            text = bot_msg.get("text", "")
            matched_key, step_idx = matcher.match(text)
            if not matched_key:
                matched_key = "unrecognized_archive"
                step_idx = 0
                status = "completed"

        terminal_keys = {
            "broadcast_completed",
            "manual_consultation",
            "user_inbound_only",
            "unrecognized_archive",
        }
        if matched_key in terminal_keys:
            status = "completed"
            next_step_key = "day_18"
            next_run_at = None
            stats["completed"] += 1
        elif step_idx is not None:
            if step_idx >= total_steps - 1 or age_days > 21:
                # Finished funnel or last step was > 21 days ago
                status = "completed"
                next_step_key = "day_18"
                next_run_at = None
                stats["completed"] += 1
            else:
                next_index = step_idx + 1
                next_step = definition.steps[next_index]
                next_step_key = next_step.key
                status = "active"
                stats["active_to_resume"] += 1

                # Stagger next_run_at between 20 and 120 minutes from now if overdue
                delay_delta = parse_delay(next_step.delay)
                calculated_next = msg_date + delay_delta
                if calculated_next < now:
                    calculated_next = now + timedelta(minutes=20 + (len(records_to_insert) % 60))
                next_run_at = calculated_next
        else:
            status = "active"
            next_step_key = "question_topic"
            next_run_at = None
            stats["active_to_resume"] += 1

        stats["matched_steps"] += 1
        step_distribution[matched_key] = step_distribution.get(matched_key, 0) + 1

        records_to_insert.append({
            "peer_id": str(peer_id),
            "matched_key": matched_key,
            "step_index": step_idx,
            "status": status,
            "next_step_key": next_step_key,
            "next_run_at": next_run_at,
            "last_msg_date": msg_date,
        })

    print("\n" + "=" * 60)
    print("VK FUNNEL RECOVERY AUDIT REPORT")
    print("=" * 60)
    print(f"Total conversations analyzed : {stats['total']}")
    print(f"Skipped group chats          : {stats['skipped_chats']}")
    print(f"Total users to register in DB: {len(records_to_insert)}")
    print(f"Active funnels to resume     : {stats['active_to_resume']}")
    print(f"Completed / Protected funnels: {stats['completed']}")
    print("\nStep Distribution:")
    for skey, count in sorted(step_distribution.items(), key=lambda x: -x[1]):
        print(f"  - {skey:30}: {count} users")
    print("=" * 60)

    if dry_run:
        print("\n[DRY RUN] Verification passed cleanly. No database changes written.")
        print("To apply to PostgreSQL, execute with --apply flag.")
        return

    # Apply to PostgreSQL
    print(f"\nApplying recovery for {len(records_to_insert)} users to PostgreSQL...")
    engine = create_async_engine(settings.database_url)
    async with AsyncSession(engine) as session:
        created_leads = 0
        created_states = 0
        for idx, rec in enumerate(records_to_insert, start=1):
            peer_id = rec["peer_id"]
            existing_identity = await session.scalar(
                select(MessengerIdentity).where(
                    MessengerIdentity.channel == "vk",
                    MessengerIdentity.external_user_id == peer_id,
                )
            )
            if existing_identity:
                lead_id = existing_identity.lead_id
            else:
                lead_id = uuid.uuid4()
                lead = Lead(
                    id=lead_id,
                    source="vk_recovery",
                    status="active",
                    created_at=rec["last_msg_date"],
                )
                session.add(lead)
                # Flush immediately so leads row exists for foreign keys
                await session.flush()

                session.add(
                    MessengerIdentity(
                        id=uuid.uuid4(),
                        lead_id=lead_id,
                        channel="vk",
                        external_user_id=peer_id,
                        is_subscribed=True,
                        subscribed_at=rec["last_msg_date"],
                        raw_profile={"source": "vk_recovery"},
                    )
                )
                session.add(
                    Conversation(
                        id=uuid.uuid4(),
                        lead_id=lead_id,
                        channel="vk",
                        source="vk",
                        status="open",
                        last_message_at=rec["last_msg_date"],
                    )
                )
                await session.flush()
                created_leads += 1

            existing_state = await session.scalar(
                select(FunnelState).where(
                    FunnelState.lead_id == lead_id,
                    FunnelState.funnel_key == definition.key,
                    FunnelState.channel == "vk",
                )
            )
            if not existing_state:
                step_idx = rec["step_index"] if rec["step_index"] is not None else 0
                state_meta = {
                    **build_state_metadata(definition=definition, step_index=step_idx),
                    FUNNEL_STARTED_AT_METADATA_KEY: rec["last_msg_date"].isoformat(),
                    CALENDAR_DAY_OFFSET_METADATA_KEY: 0,
                    "last_sent_step_key": rec["matched_key"],
                    "recovered_at": now.isoformat(),
                }
                funnel_state = FunnelState(
                    id=uuid.uuid4(),
                    lead_id=lead_id,
                    funnel_key=definition.key,
                    channel="vk",
                    status=rec["status"],
                    current_step_key=rec["next_step_key"] or rec["matched_key"],
                    next_run_at=rec["next_run_at"],
                    completed_at=rec["last_msg_date"] if rec["status"] == "completed" else None,
                    metadata_=state_meta,
                )
                session.add(funnel_state)
                await session.flush()
                created_states += 1

            if idx % 50 == 0:
                await session.commit()
                print(f"Processed and committed {idx}/{len(records_to_insert)} users...")

        await session.commit()
        done_msg = (
            f"\n[DONE] Successfully created {created_leads} leads and "
            f"{created_states} FunnelStates in PostgreSQL!"
        )
        print(done_msg)
    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(
        description="Recover VK funnel states from conversation history."
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes to PostgreSQL database")
    args = parser.parse_args()

    asyncio.run(run_recovery(dry_run=not args.apply))


if __name__ == "__main__":
    main()
