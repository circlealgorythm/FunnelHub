import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import (
    Broadcast,
    BroadcastTarget,
    Conversation,
    EmailSubscription,
    Message,
    MessengerIdentity,
)
from funnelhub.services.email_messaging import send_email_text_message
from funnelhub.services.inbox import InboxSendClients
from funnelhub.services.telegram_messaging import send_telegram_text_message
from funnelhub.services.vk_messaging import send_vk_text_message

logger = logging.getLogger(__name__)


async def _ensure_conversation(
    session: AsyncSession,
    lead_id: uuid.UUID,
    channel: str,
) -> Conversation:
    stmt = select(Conversation).where(
        Conversation.lead_id == lead_id,
        Conversation.channel == channel,
    )
    conversation = await session.scalar(stmt)
    if conversation is None:
        conversation = Conversation(
            id=uuid.uuid4(),
            lead_id=lead_id,
            channel=channel,
            status="replied",
            last_message_at=datetime.now(UTC),
        )
        session.add(conversation)
        await session.flush()
    return conversation


async def run_due_broadcasts_once(
    session: AsyncSession,
    clients: InboxSendClients,
    limit: int = 50,
) -> None:
    # Find one broadcast that needs processing
    stmt = select(Broadcast).where(
        Broadcast.status.in_(["created", "processing"])
    ).order_by(Broadcast.created_at.asc()).limit(1)
    
    broadcast = await session.scalar(stmt)
    if not broadcast:
        return

    if broadcast.status == "created":
        broadcast.status = "processing"
        await session.flush()

    target_stmt = select(BroadcastTarget).where(
        BroadcastTarget.broadcast_id == broadcast.id,
        BroadcastTarget.status == "pending",
    ).limit(limit)
    targets = (await session.scalars(target_stmt)).all()

    if not targets:
        broadcast.status = "completed"
        await session.flush()
        return

    for target in targets:
        # For MVP, we will send to all requested channels
        success_any = False
        error_messages = []
        
        for channel in broadcast.channels:
            try:
                # Check subscription
                if channel in ("telegram", "vk"):
                    id_stmt = select(MessengerIdentity).where(
                        MessengerIdentity.lead_id == target.lead_id,
                        MessengerIdentity.channel == channel,
                        MessengerIdentity.is_subscribed.is_(True),
                    ).order_by(MessengerIdentity.created_at.desc())
                    identity = await session.scalar(id_stmt)
                    if not identity:
                        error_messages.append(f"{channel}: unsubscribed or not linked")
                        continue
                elif channel == "email":
                    sub_stmt = select(EmailSubscription).where(
                        EmailSubscription.lead_id == target.lead_id
                    )
                    sub = await session.scalar(sub_stmt)
                    if not sub or sub.status != "subscribed":
                        error_messages.append("email: unsubscribed or no email")
                        continue
                
                conversation = await _ensure_conversation(session, target.lead_id, channel)
                
                # Send message
                if channel == "telegram" and clients.telegram_bot:
                    res_tg = await send_telegram_text_message(
                        session=session,
                        bot=clients.telegram_bot,
                        lead_id=target.lead_id,
                        text=broadcast.message_text,
                    )
                    message_id = res_tg.message_id
                elif channel == "vk" and clients.vk_client:
                    res_vk = await send_vk_text_message(
                        session=session,
                        client=clients.vk_client,
                        lead_id=target.lead_id,
                        text=broadcast.message_text,
                    )
                    message_id = res_vk.message_id
                elif channel == "email" and clients.email_client:
                    res_email = await send_email_text_message(
                        session=session,
                        client=clients.email_client,
                        lead_id=target.lead_id,
                        subject=clients.email_subject,
                        text=broadcast.message_text,
                        public_base_url=clients.public_base_url,
                        from_email=clients.email_from_email,
                        from_name=clients.email_from_name,
                        signature_image_url=clients.email_signature_image_url,
                        metadata={"source": "manual_broadcast"},
                    )
                    message_id = res_email.message_id
                else:
                    error_messages.append(f"{channel}: client not configured")
                    continue
                
                message = await session.get(Message, message_id)
                if message:
                    message.conversation_id = conversation.id
                    conversation.last_message_at = message.sent_at or datetime.now(UTC)
                success_any = True
                
            except Exception as exc:
                error_messages.append(f"{channel}: {exc}")
                logger.warning(
                    "Broadcast %s failed to send to lead %s via %s: %s",
                    broadcast.id,
                    target.lead_id,
                    channel,
                    exc,
                )

        if success_any:
            target.status = "sent"
            broadcast.processed_leads += 1
        else:
            if all(
                "unsubscribed" in msg or "not linked" in msg or "no email" in msg
                for msg in error_messages
            ):
                target.status = "skipped_unsubscribed"
                target.error = "; ".join(error_messages)
                broadcast.skipped_leads += 1
                broadcast.processed_leads += 1
            else:
                target.status = "failed"
                target.error = "; ".join(error_messages)
                broadcast.failed_leads += 1
                broadcast.processed_leads += 1

        await session.flush()
    
    await session.commit()
