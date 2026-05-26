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
from narrative_quest_engine import ParagonAIDirector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SimulationScheduler")


async def trigger_paragon_social_loop(pool):
    import json
    logger.info("Running Paragon Social-Choice Loop...")
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT cell_id, active_chaos_tag, civilization_profile FROM global_simulation_cells WHERE active_chaos_tag IS NOT NULL;")

        director = ParagonAIDirector(pool)

        for row in rows:
            tag = row["active_chaos_tag"]
            try:
                # The requirement says: "sectors where active_chaos_tag > 0.5"
                if float(tag) > 0.5:
                    civ_profile = row["civilization_profile"]
                    if isinstance(civ_profile, str):
                        civ_profile = json.loads(civ_profile)
                    civ_profile = civ_profile or {}

                    dilemma = director.generate_dilemma(row["cell_id"], tag, civ_profile)

                    # Store the Paragon's chosen action and resulting impact
                    payload = json.dumps({
                        "action": dilemma["mechanical_intent"],
                        "summary": dilemma["decision_summary"]
                    })

                    # Insert into player_saga_stack table. Using the zero UUID for the AI Paragon events without a specific real player.
                    await conn.execute(
                        """
                        INSERT INTO player_saga_stack (character_id, target_cell_id, event_type, context_payload)
                        VALUES ('00000000-0000-0000-0000-000000000000', $1, 'Paragon Dilemma Choice', $2)
                        """,
                        row["cell_id"],
                        payload
                    )
            except ValueError:
                # Ignored if tag is not a float (e.g., "#Epicenter")
                pass

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
        DATABASE_URL = os.getenv("DATABASE_URL")
        if not DATABASE_URL:
            logger.error("DATABASE_URL environment variable is missing. Cannot start scheduler.")
            return

        pool = None
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

            await trigger_paragon_social_loop(pool)

            logger.info("All sub-engines executed successfully.")
        except Exception as e:
            logger.error(f"Error executing sub-engines: {e}")
        finally:
            if pool:
                await pool.close()
                logger.info("Database pool safely closed.")

if __name__ == "__main__":
    asyncio.run(master_hourly_tick())
