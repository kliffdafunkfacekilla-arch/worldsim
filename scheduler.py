import asyncio
import time
import logging
from uuid import uuid4
from datetime import datetime, timezone
import os

# Sub-engine imports
from chaos_orbit_engine import update_all_chaos_resonances
from ecology_matrix_engine import resolve_ecological_turn
from shadow_subversion_engine import update_shadow_war_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SimulationScheduler")

async def master_hourly_tick():
    """
    Background scheduler execution file that advances the world clock.
    Every real-world hour, advances the game world clock by exactly +6 Hours (1 Segment/Watch).
    Triggers macro sub-engines to calculate 90,000 region calculations.
    """
    logger.info("Initializing Master Scheduler loop. Waiting for tick...")
    while True:
        # Wait 1 Real World Hour (3600 seconds). For testing, could use a smaller value.
        await asyncio.sleep(3600)

        logger.info(f"[{datetime.now(timezone.utc).isoformat()}] Hourly tick triggered. Executing sub-engines...")

        import asyncpg

        # We need a db pool connection to pass to the engines if they require it.
        DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:PigPig3897!!@localhost:5432/worldsim")

        try:
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)

            # Advance world clock by 6 hours (1 Segment/Watch)
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE system_clock
                    SET current_segment = (current_segment + 6) % 24,
                        current_day = CASE WHEN (current_segment + 6) >= 24 THEN current_day + 1 ELSE current_day END
                    WHERE id = 1;
                """)

            # Run sub engines
            logger.info("Running chaos_orbit_engine...")
            await update_all_chaos_resonances(pool)
            logger.info("Running ecology_matrix_engine...")
            await resolve_ecological_turn(pool)
            logger.info("Running shadow_subversion_engine...")
            await update_shadow_war_state(pool)

            logger.info("All sub-engines executed successfully.")
            await pool.close()
        except Exception as e:
            logger.error(f"Error executing sub-engines: {e}")

if __name__ == "__main__":
    asyncio.run(master_hourly_tick())
