import os
import math
import asyncio
import logging
import asyncpg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chaos_orbit_engine")

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:PigPig3897!!@localhost:5432/worldsim")

class CanonicalChaosOrbitEngine:
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url

    async def advance_clock(self) -> dict:
        """
        Advances the system clock by one segment in an atomic transaction.
        Handles wrap-around: 24 segments per day, 360 days per year.
        Returns the new clock state.
        """
        logger.info("Advancing system clock segment...")
        conn = await asyncpg.connect(self.db_url)
        try:
            async with conn.transaction():
                # Atomically update segment, wrapping and cascading to days/years
                row = await conn.fetchrow(
                    """
                    UPDATE system_clock
                    SET 
                        current_segment = (current_segment + 1) % 24,
                        current_day = CASE WHEN current_segment = 23 THEN (current_day % 360) + 1 ELSE current_day END,
                        current_year = CASE WHEN current_segment = 23 AND current_day = 360 THEN current_year + 1 ELSE current_year END
                    WHERE id = 1
                    RETURNING current_year, current_day, current_segment;
                    """
                )
                if not row:
                    raise Exception("Failed to increment system clock; system_clock table may be empty.")
                
                clock_state = dict(row)
                logger.info(f"Clock advanced: Year {clock_state['current_year']}, Day {clock_state['current_day']}, Segment {clock_state['current_segment']}")
                
                # Update moon coordinates based on the new clock segment
                await self._update_moon_orbitals(conn, clock_state['current_segment'])
                
                return clock_state
        finally:
            await conn.close()

    async def _update_moon_orbitals(self, conn: asyncpg.Connection, current_segment: int):
        """
        Retrieves and logs the moon orbital coordinates (moon_focal_x, moon_focal_y)
        for the current segment from calendar_configuration.
        """
        logger.info("Retrieving moon orbital coordinates...")
        row = await conn.fetchrow(
            "SELECT segment_name, moon_focal_x, moon_focal_y FROM calendar_configuration WHERE segment_id = $1;",
            current_segment
        )
        if row:
            logger.info(f"Moon is at '{row['segment_name']}' coordinates=({float(row['moon_focal_x'])}, {float(row['moon_focal_y'])})")
        else:
            logger.warning(f"No trajectory configuration found for segment {current_segment}")

    async def project_chaos_vectors(self):
        """
        Project cosmic vectors from the moon to the 12 sovereign cosmic anchors,
        warping reality in intersecting cells.
        """
        logger.info("Projecting chaos vectors...")
        conn = await asyncpg.connect(self.db_url)
        try:
            async with conn.transaction():
                # 1. Reset all cell active_chaos_tag values to #StableReality
                logger.info("Resetting all grid cells to '#StableReality'...")
                await conn.execute(
                    "UPDATE global_simulation_cells SET active_chaos_tag = '#StableReality';"
                )
                
                # 2. Retrieve current clock segment
                clock = await conn.fetchrow(
                    "SELECT current_segment FROM system_clock WHERE id = 1;"
                )
                if not clock:
                    logger.warning("No system clock state found. Skipping vector projection.")
                    return
                current_segment = clock["current_segment"]

                # Retrieve moon coordinates for current clock segment
                moon = await conn.fetchrow(
                    """
                    SELECT moon_focal_x, moon_focal_y 
                    FROM calendar_configuration 
                    WHERE segment_id = $1;
                    """,
                    current_segment
                )
                if not moon:
                    logger.warning(f"No trajectory configuration found for segment {current_segment}. Skipping vector projection.")
                    return
                
                mx = float(moon["moon_focal_x"])
                my = float(moon["moon_focal_y"])
                logger.info(f"Current Moon focal origin for segment {current_segment}: ({mx}, {my})")
                
                # 3. Retrieve the 12 anchors
                anchors = await conn.fetch(
                    """
                    SELECT a.coord_x, a.coord_y, p.name AS power_tag
                    FROM spatial_sovereign_anchors a
                    JOIN sovereign_cosmic_powers p ON a.associated_power_id = p.power_id
                    WHERE a.active_status = TRUE;
                    """
                )
                
                # 4. Project vectors by updating cells directly in SQL using parameterized queries
                for anchor in anchors:
                    ax, ay = anchor["coord_x"], anchor["coord_y"]
                    power_tag = anchor["power_tag"]
                    
                    logger.info(f"Projecting '{power_tag}' vector from moon ({mx}, {my}) to anchor ({ax}, {ay})...")
                    
                    # Update cells intersecting the line segment within radius of 6.5 units.
                    # We restrict scans using a bounding box coord_x and coord_y.
                    await conn.execute(
                        """
                        WITH project_t AS (
                            SELECT 
                                cell_id,
                                GREATEST(0.0, LEAST(1.0, 
                                    ((coord_x - $2) * ($3 - $2) + (coord_y - $4) * ($5 - $4))::float / 
                                    NULLIF((($3 - $2)^2 + ($5 - $4)^2)::float, 0.0)
                                )) AS t
                            FROM global_simulation_cells
                            WHERE coord_x BETWEEN LEAST($2, $3) - 7 AND GREATEST($2, $3) + 7
                              AND coord_y BETWEEN LEAST($4, $5) - 7 AND GREATEST($4, $5) + 7
                        )
                        UPDATE global_simulation_cells g
                        SET active_chaos_tag = $1
                        FROM project_t p
                        WHERE g.cell_id = p.cell_id
                          AND (
                            (g.coord_x - ($2 + p.t * ($3 - $2)))^2 + 
                            (g.coord_y - ($4 + p.t * ($5 - $4)))^2
                          ) <= 42.25;
                        """,
                        power_tag, mx, ax, my, ay
                    )

                # 5. Lock in exact anchor epicenter tags permanently
                logger.info("Locking anchor epicenter tags...")
                await conn.execute(
                    """
                    UPDATE global_simulation_cells c
                    SET active_chaos_tag = '#Epicenter_' || p.name
                    FROM spatial_sovereign_anchors a
                    JOIN sovereign_cosmic_powers p ON a.associated_power_id = p.power_id
                    WHERE c.coord_x = a.coord_x AND c.coord_y = a.coord_y;
                    """
                )
                logger.info("Chaos vector projection sequence completed successfully.")
        finally:
            await conn.close()

async def main():
    engine = CanonicalChaosOrbitEngine()
    # Advance clock and project vectors
    await engine.advance_clock()
    await engine.project_chaos_vectors()
    
    # Run scavenger sweep garbage collection
    try:
        from persistency_manager import execute_garbage_collection_sweep
        await execute_garbage_collection_sweep()
    except Exception as e:
        logger.error(f"Failed to run scavenger sweep garbage collection: {e}")

if __name__ == "__main__":
    asyncio.run(main())
