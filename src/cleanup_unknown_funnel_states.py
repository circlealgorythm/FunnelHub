import asyncio
import logging
from sqlalchemy import select, delete
from funnelhub.db.models import FunnelState
from funnelhub.db.session import async_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def cleanup_unknown_states():
    async with async_session_factory() as session:
        # Find all unknown states
        unknown_states = (
            await session.scalars(
                select(FunnelState).where(FunnelState.channel == "unknown")
            )
        ).all()
        
        logger.info(f"Found {len(unknown_states)} unknown funnel states.")
        
        count = 0
        for state in unknown_states:
            # Check if there's a valid state for the same lead and funnel
            valid_states = (
                await session.scalars(
                    select(FunnelState).where(
                        FunnelState.lead_id == state.lead_id,
                        FunnelState.funnel_key == state.funnel_key,
                        FunnelState.channel != "unknown"
                    )
                )
            ).all()
            
            if valid_states:
                logger.info(f"Deleting unknown state {state.id} for lead {state.lead_id} (found valid alternative)")
                await session.delete(state)
                count += 1
            else:
                logger.info(f"Keeping unknown state {state.id} for lead {state.lead_id} (no valid alternative)")
                
        if count > 0:
            await session.commit()
            logger.info(f"Deleted {count} stale unknown states.")
        else:
            logger.info("Nothing to delete.")

if __name__ == "__main__":
    asyncio.run(cleanup_unknown_states())
