import os
import json
import asyncio
import logging
import random
import asyncpg
from advanced_civilization_engine import FactionLogisticsEngine, TIER_VALUES, get_tier_from_pop, scale_species_profile, get_default_species_dict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civ_expansion_engine")

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:PigPig3897!!@localhost:5432/worldsim")

class CivilizationExpansionEngine:
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url

    async def auto_seed_if_needed(self, conn):
        """
        Seeds the database with three starting settlements if the map is empty of faction cells.
        Enriches starting profiles with logistics, treasury, and Paragon agents.
        """
        logger.info("Checking if database requires auto-seeding...")
        count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM global_simulation_cells
            WHERE (civilization_profile->>'faction' IS NOT NULL AND civilization_profile->>'faction' != '#Independent')
               OR (civilization_profile->>'controlling_faction_id' IS NOT NULL);
            """
        )
        if count > 0:
            logger.info(f"Database already has {count} aligned cells. Skipping seeding.")
            return

        logger.info("No aligned settlements found. Registering factions and seeding default cities...")
        
        # Register factions in registry
        await conn.execute(
            """
            INSERT INTO registry_factions (faction_name, ideology_type) VALUES
            ('#GorgonHorde', 'Expansionist'),
            ('#CinderClaw', 'Survivalist'),
            ('#IronClan', 'Industrialist')
            ON CONFLICT (faction_name) DO NOTHING;
            """
        )

        # Coordinates for starting cities with logistics and Paragons
        seeds = [
            (100, 100, {
                "faction": "#GorgonHorde",
                "controlling_faction_id": "#GorgonHorde",
                "population": 800,
                "tier": "Town",
                "has_settlement": True,
                "reactors": 1,
                "dragonstone_shards": 10,
                "development_index": 0.5,
                "species": {"Gorgons": 800},
                "happiness": 0.5,
                "security": 0.50,
                "treasury": {"wealth": 150.0},
                "unlocked_travel_types": ["Caravans"],
                "crime_rate": 0.1,
                "cartel_saturation": 0.1,
                "cartel_roster_size": 5,
                "active_airships": 0,
                "morbidity_and_trauma_matrix": {"narcotic_addiction": 0.0, "alcohol_dependence": 0.0},
                "paragons": [
                    {
                        "name": "General Vraka",
                        "role": "Ruling Paragon",
                        "is_criminal": False,
                        "personal_goals": ["Subjugate neighbors", "Amass stockpiles"],
                        "traits": ["expansionist", "aggressive"]
                    }
                ]
            }),
            (150, 150, {
                "faction": "#CinderClaw",
                "controlling_faction_id": "#CinderClaw",
                "population": 2500,
                "tier": "City",
                "has_settlement": True,
                "reactors": 2,
                "dragonstone_shards": 25,
                "development_index": 0.7,
                "species": {"CinderClaws": 2500},
                "happiness": 0.5,
                "security": 0.50,
                "treasury": {"wealth": 300.0},
                "unlocked_travel_types": ["Caravans"],
                "crime_rate": 0.15,
                "cartel_saturation": 0.15,
                "cartel_roster_size": 5,
                "active_airships": 0,
                "morbidity_and_trauma_matrix": {"narcotic_addiction": 0.0, "alcohol_dependence": 0.0},
                "paragons": [
                    {
                        "name": "Eldest Ignis",
                        "role": "Ruling Paragon",
                        "is_criminal": False,
                        "personal_goals": ["Secure resources", "Protect the clutch"],
                        "traits": ["cautious", "protective"]
                    }
                ]
            }),
            (200, 200, {
                "faction": "#IronClan",
                "controlling_faction_id": "#IronClan",
                "population": 11000,
                "tier": "Metropolis",
                "has_settlement": True,
                "reactors": 3,
                "dragonstone_shards": 50,
                "development_index": 0.9,
                "species": {"IronClans": 11000},
                "happiness": 0.5,
                "security": 0.50,
                "treasury": {"wealth": 600.0},
                "unlocked_travel_types": ["Caravans", "Steampunk Airships"],
                "crime_rate": 0.05,
                "cartel_saturation": 0.05,
                "cartel_roster_size": 5,
                "active_airships": 1,
                "morbidity_and_trauma_matrix": {"narcotic_addiction": 0.0, "alcohol_dependence": 0.0},
                "paragons": [
                    {
                        "name": "Overseer Ironfist",
                        "role": "Ruling Paragon",
                        "is_criminal": False,
                        "personal_goals": ["Maximize factory output", "Maintain order"],
                        "traits": ["industrialist", "orderly"]
                    },
                    {
                        "name": "Captain Steelclad",
                        "role": "Guard Captain",
                        "is_criminal": False,
                        "personal_goals": ["Defend boundaries", "Fund city patrols"],
                        "traits": ["dutiful", "vigilant"]
                    }
                ]
            })
        ]

        for x, y, profile in seeds:
            flora = {"biomass_volume": 100.0, "biomass_index": 1.0, "growth_stage": "flourishing"}
            await conn.execute(
                """
                UPDATE global_simulation_cells
                SET 
                    civilization_profile = $1,
                    flora_biomass_data = $2,
                    active_chaos_tag = '#StableReality'
                WHERE coord_x = $3 AND coord_y = $4;
                """,
                json.dumps(profile), json.dumps(flora), x, y
            )
            logger.info(f"Seeded {profile['faction']} settlement at ({x}, {y})")

    async def run_civilization_cycle(self):
        """
        Runs the full advanced civilization logistics and skirmish cycle.
        """
        logger.info("Initializing advanced FactionLogisticsEngine transaction...")
        
        # Create connection pool
        pool = await asyncpg.create_pool(self.db_url, min_size=1, max_size=2)
        try:
            # Check auto-seed first
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await self.auto_seed_if_needed(conn)
                    
            # Instantiate the Logistics Engine and run it
            engine = FactionLogisticsEngine(pool)
            await engine.execute_simulation_turn()
            
        except Exception as e:
            logger.error(f"Error running FactionLogisticsEngine turn: {e}")
            raise e
        finally:
            await pool.close()

async def main():
    engine = CivilizationExpansionEngine()
    await engine.run_civilization_cycle()

if __name__ == "__main__":
    asyncio.run(main())
