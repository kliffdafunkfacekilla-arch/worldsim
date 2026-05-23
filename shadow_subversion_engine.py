import os
import json
import asyncio
import logging
import asyncpg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shadow_subversion_engine")

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:PigPig3897!!@localhost:5432/worldsim")

# Tier weight mappings
TIER_WEIGHTS = {
    "Metropolis": 5,
    "City": 4,
    "Town": 3,
    "Village": 2,
    "Camp": 1,
    "Wilderness": 0,
    "Ruins": 0
}

class ShadowSubversionEngine:
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
        self.cache = {}

    async def init_tuners(self, conn):
        """
        Ensures the global_simulation_tuners table exists and has default tuners seeded.
        """
        logger.info("Initializing global_simulation_tuners table...")
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS global_simulation_tuners (
                id INTEGER PRIMARY KEY DEFAULT 1,
                cult_base_growth REAL NOT NULL DEFAULT 0.005,
                cult_urban_mult REAL NOT NULL DEFAULT 0.015,
                cult_chaos_surge REAL NOT NULL DEFAULT 0.12,
                cult_contagion_rate REAL NOT NULL DEFAULT 0.03,
                warden_base_growth REAL NOT NULL DEFAULT 0.01,
                warden_suppression_power REAL NOT NULL DEFAULT 0.05,
                CONSTRAINT chk_global_simulation_tuners_single_row CHECK (id = 1)
            );
            """
        )
        await conn.execute(
            """
            INSERT INTO global_simulation_tuners (
                id, cult_base_growth, cult_urban_mult, cult_chaos_surge, cult_contagion_rate, warden_base_growth, warden_suppression_power
            ) VALUES (1, 0.005, 0.015, 0.12, 0.03, 0.01, 0.05)
            ON CONFLICT (id) DO NOTHING;
            """
        )

    async def get_tuners(self, conn) -> dict:
        row = await conn.fetchrow("SELECT * FROM global_simulation_tuners WHERE id = 1;")
        return dict(row)

    async def get_cell(self, conn, cell_id=None, coord_x=None, coord_y=None):
        if cell_id is not None and cell_id in self.cache:
            return self.cache[cell_id]
        
        for c in self.cache.values():
            if coord_x is not None and coord_y is not None and c["coord_x"] == coord_x and c["coord_y"] == coord_y:
                return c

        if cell_id is not None:
            row = await conn.fetchrow(
                """
                SELECT cell_id, coord_x, coord_y, active_chaos_tag, flora_biomass_data, fauna_population_data, civilization_profile, shadow_war_metrics
                FROM global_simulation_cells WHERE cell_id = $1;
                """, cell_id
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT cell_id, coord_x, coord_y, active_chaos_tag, flora_biomass_data, fauna_population_data, civilization_profile, shadow_war_metrics
                FROM global_simulation_cells WHERE coord_x = $1 AND coord_y = $2;
                """, coord_x, coord_y
            )

        if not row:
            return None

        cell = {
            "cell_id": row["cell_id"],
            "coord_x": row["coord_x"],
            "coord_y": row["coord_y"],
            "active_chaos_tag": row["active_chaos_tag"],
            "flora_biomass_data": json.loads(row["flora_biomass_data"]),
            "fauna_population_data": json.loads(row["fauna_population_data"]),
            "civilization_profile": json.loads(row["civilization_profile"]),
            "shadow_war_metrics": json.loads(row["shadow_war_metrics"]),
            "is_dirty": False
        }
        self.cache[cell["cell_id"]] = cell
        return cell

    async def run_shadow_cycle(self):
        logger.info("Connecting to database for Shadow War cycle...")
        conn = await asyncpg.connect(self.db_url)
        try:
            # Step 1: Ensure database tuners are initialized
            async with conn.transaction():
                await self.init_tuners(conn)
                tuners = await self.get_tuners(conn)

            # Retrieve tuner values
            cult_base_growth = float(tuners["cult_base_growth"])
            cult_urban_mult = float(tuners["cult_urban_mult"])
            cult_chaos_surge = float(tuners["cult_chaos_surge"])
            cult_contagion_rate = float(tuners["cult_contagion_rate"])
            warden_base_growth = float(tuners["warden_base_growth"])
            warden_suppression_power = float(tuners["warden_suppression_power"])

            async with conn.transaction():
                # Fetch all civilized cells (aligned to a faction other than Independent and Cult_Inverted)
                civilized_rows = await conn.fetch(
                    """
                    SELECT cell_id FROM global_simulation_cells
                    WHERE (civilization_profile->>'faction' IS NOT NULL 
                           AND civilization_profile->>'faction' != '#Independent'
                           AND civilization_profile->>'faction' != '#Cult_Inverted')
                       OR (civilization_profile->>'controlling_faction_id' IS NOT NULL
                           AND civilization_profile->>'controlling_faction_id' != '#Independent'
                           AND civilization_profile->>'controlling_faction_id' != '#Cult_Inverted');
                    """
                )
                civilized_ids = [row["cell_id"] for row in civilized_rows]
                logger.info(f"Processing infiltration and warden scan for {len(civilized_ids)} civilized cells...")

                # 1. Cult Infiltration & 2. Autonomous Warden Scan Steps
                for cell_id in civilized_ids:
                    cell = await self.get_cell(conn, cell_id=cell_id)
                    if not cell:
                        continue
                    
                    metrics = cell["shadow_war_metrics"]
                    profile = cell["civilization_profile"]
                    
                    # Parse values, supporting dual keys for absolute compatibility
                    cult_index = float(metrics.get("cult_infiltration_index", metrics.get("subversion", 0.0)))
                    warden_index = float(metrics.get("warden_presence", metrics.get("infiltration", 0.0)))
                    tier = profile.get("tier", "Wilderness")
                    weight = TIER_WEIGHTS.get(tier, 0)
                    
                    # Infiltration growth calculation
                    growth = cult_base_growth + (cult_urban_mult * weight)
                    
                    # Chaos surge modifier
                    active_tag = cell["active_chaos_tag"]
                    if active_tag and active_tag != "#StableReality":
                        growth += cult_chaos_surge
                        
                    # Warden suppression deduction
                    new_cult_index = cult_index + growth - (warden_index * warden_suppression_power)
                    new_cult_index = max(0.0, min(1.0, new_cult_index))

                    # Warden Scan calculation
                    if new_cult_index > 0.25:
                        new_warden_index = warden_index + warden_base_growth
                    else:
                        new_warden_index = warden_index - 0.02
                    new_warden_index = max(0.0, min(1.0, new_warden_index))

                    # Save both sets of keys to be 100% compatible
                    metrics["cult_infiltration_index"] = new_cult_index
                    metrics["subversion"] = new_cult_index
                    metrics["warden_presence"] = new_warden_index
                    metrics["infiltration"] = new_warden_index
                    
                    cell["is_dirty"] = True

                # 3. Contagion Spillover Step
                # Find all cells in cache or DB where subversion or infiltration is > 0.60
                logger.info("Evaluating contagion spillover hot zones...")
                hot_zone_rows = await conn.fetch(
                    """
                    SELECT cell_id FROM global_simulation_cells
                    WHERE COALESCE((shadow_war_metrics->>'cult_infiltration_index')::float, (shadow_war_metrics->>'subversion')::float, 0.0) > 0.60
                       OR COALESCE((shadow_war_metrics->>'warden_presence')::float, (shadow_war_metrics->>'infiltration')::float, 0.0) > 0.60;
                    """
                )
                
                # Fetch hot zones into cache
                for hz_row in hot_zone_rows:
                    await self.get_cell(conn, cell_id=hz_row["cell_id"])

                # Make a list of hot zones to process so we don't mutate during iteration
                hot_zones = []
                for cell in list(self.cache.values()):
                    metrics = cell["shadow_war_metrics"]
                    c_index = float(metrics.get("cult_infiltration_index", metrics.get("subversion", 0.0)))
                    w_index = float(metrics.get("warden_presence", metrics.get("infiltration", 0.0)))
                    if c_index > 0.60 or w_index > 0.60:
                        hot_zones.append((cell, c_index, w_index))

                logger.info(f"Found {len(hot_zones)} active hot zones. Leaking contagion...")
                for hz_cell, c_val, w_val in hot_zones:
                    cx = hz_cell["coord_x"]
                    cy = hz_cell["coord_y"]
                    
                    # Query all 8 neighbors of the hot zone
                    neighbor_rows = await conn.fetch(
                        """
                        SELECT cell_id FROM global_simulation_cells
                        WHERE coord_x BETWEEN $1 - 1 AND $1 + 1
                          AND coord_y BETWEEN $2 - 1 AND $2 + 1
                          AND NOT (coord_x = $1 AND coord_y = $2)
                          AND coord_x >= 0 AND coord_x < 300
                          AND coord_y >= 0 AND coord_y < 300;
                        """,
                        cx, cy
                    )
                    
                    for n_row in neighbor_rows:
                        neighbor = await self.get_cell(conn, cell_id=n_row["cell_id"])
                        if not neighbor:
                            continue
                        
                        n_metrics = neighbor["shadow_war_metrics"]
                        dirty = False
                        
                        if c_val > 0.60:
                            n_c = float(n_metrics.get("cult_infiltration_index", n_metrics.get("subversion", 0.0)))
                            new_n_c = max(0.0, min(1.0, n_c + cult_contagion_rate))
                            n_metrics["cult_infiltration_index"] = new_n_c
                            n_metrics["subversion"] = new_n_c
                            dirty = True
                            
                        if w_val > 0.60:
                            n_w = float(n_metrics.get("warden_presence", n_metrics.get("infiltration", 0.0)))
                            # Warden contagion leaks at half the cult contagion rate or warden_base_growth
                            new_n_w = max(0.0, min(1.0, n_w + (warden_base_growth * 0.5)))
                            n_metrics["warden_presence"] = new_n_w
                            n_metrics["infiltration"] = new_n_w
                            dirty = True
                            
                        if dirty:
                            neighbor["is_dirty"] = True

                # 4. Critical Shatter-Point Inversion Step
                # Scan all cells in cache or DB where cult_infiltration_index >= 1.0 and faction is not #Cult_Inverted or #Independent
                logger.info("Checking for Shatter-Point Inversions...")
                shatter_candidates = []
                for cell in list(self.cache.values()):
                    metrics = cell["shadow_war_metrics"]
                    c_index = float(metrics.get("cult_infiltration_index", metrics.get("subversion", 0.0)))
                    profile = cell["civilization_profile"]
                    faction = profile.get("faction", "#Independent")
                    if c_index >= 1.0 and faction != "#Independent" and faction != "#Cult_Inverted":
                        shatter_candidates.append(cell)
                
                # Double-check database for other cells not yet in cache that might have subversion >= 1.0
                db_shatter_rows = await conn.fetch(
                    """
                    SELECT cell_id FROM global_simulation_cells
                    WHERE COALESCE((shadow_war_metrics->>'cult_infiltration_index')::float, (shadow_war_metrics->>'subversion')::float, 0.0) >= 1.0
                      AND civilization_profile->>'faction' IS NOT NULL
                      AND civilization_profile->>'faction' != '#Independent'
                      AND civilization_profile->>'faction' != '#Cult_Inverted';
                    """
                )
                for ds_row in db_shatter_rows:
                    cand = await self.get_cell(conn, cell_id=ds_row["cell_id"])
                    if cand and cand not in shatter_candidates:
                        shatter_candidates.append(cand)

                for cell in shatter_candidates:
                    profile = cell["civilization_profile"]
                    fauna = cell["fauna_population_data"]
                    
                    old_faction = profile.get("faction", "#Independent")
                    old_pop = int(profile.get("population", 0))
                    new_pop = int(old_pop * 0.15)
                    
                    # Forcefully collapse the city
                    profile["name"] = "Inverted Ruins"
                    profile["tier"] = "Ruins"
                    profile["population"] = new_pop
                    profile["faction"] = "#Cult_Inverted"
                    profile["controlling_faction_id"] = "#Cult_Inverted"
                    profile["has_settlement"] = True
                    profile["reactors"] = 0
                    profile["dragonstone_shards"] = 0
                    
                    # Replace fauna with Abyssal Horrors
                    fauna["populations"] = [{"species": "Abyssal_Horrors", "density": 1.0}]
                    fauna["total_count"] = 1
                    fauna["dominant_species_id"] = "Abyssal_Horrors"
                    fauna["dominant_species"] = "Abyssal_Horrors"
                    
                    # Set active chaos tag
                    current_tag = cell["active_chaos_tag"]
                    if current_tag == "#StableReality" or not current_tag:
                        cell["active_chaos_tag"] = "#Epicenter_#Void_Fracture"
                    else:
                        if current_tag.startswith("#Epicenter_"):
                            cell["active_chaos_tag"] = current_tag
                        else:
                            cell["active_chaos_tag"] = f"#Epicenter_{current_tag}"
                            
                    cell["is_dirty"] = True
                    logger.critical(
                        f"SHATTER-POINT INVERSION in cell {cell['cell_id']} ({cell['coord_x']}, {cell['coord_y']})! "
                        f"Faction {old_faction} collapsed to #Cult_Inverted. Tier dropped to Ruins. Name set to 'Inverted Ruins'. "
                        f"Population slaughtered {old_pop} -> {new_pop}. Species replaced with Abyssal_Horrors. Tag set to {cell['active_chaos_tag']}."
                    )

                # Save all dirty cells back to the database
                dirty_cells = [c for c in self.cache.values() if c["is_dirty"]]
                logger.info(f"Saving {len(dirty_cells)} updated cell records to database...")
                for cell in dirty_cells:
                    await conn.execute(
                        """
                        UPDATE global_simulation_cells
                        SET 
                            active_chaos_tag = $1,
                            flora_biomass_data = $2,
                            fauna_population_data = $3,
                            civilization_profile = $4,
                            shadow_war_metrics = $5
                        WHERE cell_id = $6;
                        """,
                        cell["active_chaos_tag"],
                        json.dumps(cell["flora_biomass_data"]),
                        json.dumps(cell["fauna_population_data"]),
                        json.dumps(cell["civilization_profile"]),
                        json.dumps(cell["shadow_war_metrics"]),
                        cell["cell_id"]
                    )
                logger.info("Shadow war simulation tick complete and committed.")

        except Exception as e:
            logger.error(f"Error running Shadow War cycle: {e}")
            raise e
        finally:
            await conn.close()

async def main():
    engine = ShadowSubversionEngine()
    await engine.run_shadow_cycle()

if __name__ == "__main__":
    asyncio.run(main())
