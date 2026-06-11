import asyncio
import logging
from collections.abc import Sequence

from sqlalchemy import select

from funnelhub.db.models import FunnelState
from funnelhub.db.session import async_session_maker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def cleanup_unknown_states() -> None:
    async with async_session_maker() as session:
        # Find all unknown states
        unknown_states: Sequence[FunnelState] = (
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
                        FunnelState.channel != "unknown",
                    )
                )
            ).all()

            if valid_states:
                logger.info(
                    "Deleting unknown state %s for lead %s (found valid alternative)",
                    state.id,
                    state.lead_id,
                )
                await session.delete(state)
                count += 1
            else:
                logger.info(
                    "Keeping unknown state %s for lead %s (no valid alternative)",
                    state.id,
                    state.lead_id,
                )

        if count > 0:
            await session.commit()
            logger.info(f"Deleted {count} stale unknown states.")
        else:
            logger.info("Nothing to delete.")


if __name__ == "__main__":
    asyncio.run(cleanup_unknown_states())
