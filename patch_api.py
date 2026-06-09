
code = '''
class BroadcastTargetResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str | None
    lead_contact: str | None
    status: str
    error: str | None

class BroadcastTargetListResponse(BaseModel):
    items: list[BroadcastTargetResponse]
    total: int

@router.get("/{broadcast_id}/targets", response_model=BroadcastTargetListResponse)
async def get_broadcast_targets(
    broadcast_id: uuid.UUID,
    session: SessionDep,
    limit: int = 100,
    offset: int = 0,
) -> BroadcastTargetListResponse:
    from sqlalchemy import select, func
    from funnelhub.db.models import BroadcastTarget, Lead

    count_stmt = select(func.count()).select_from(BroadcastTarget).where(BroadcastTarget.broadcast_id == broadcast_id)
    total = int(await session.scalar(count_stmt) or 0)

    stmt = select(BroadcastTarget, Lead).join(Lead).where(BroadcastTarget.broadcast_id == broadcast_id).order_by(BroadcastTarget.created_at.asc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).all()

    items = []
    for target, lead in rows:
        items.append(BroadcastTargetResponse(
            id=target.id,
            lead_id=target.lead_id,
            lead_name=lead.name or lead.first_name,
            lead_contact=lead.email or lead.phone or lead.telegram,
            status=target.status,
            error=target.error,
        ))

    return BroadcastTargetListResponse(items=items, total=total)
'''

with open('src/funnelhub/api/broadcasts.py', 'a', encoding='utf-8') as f:
    f.write(code)
