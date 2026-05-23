import os
import json
import asyncio
import logging
import random
import asyncpg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("civ_expansion_engine")

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:PigPig3897!!@localhost:5432/worldsim")

# Tier thresholds and value mappings
TIER_VALUES = {
    "Wilderness": 0,
    "Refugee_Camp": 1,
    "Camp": 1,
    "State_of_Emergency": 2,
    "Village": 2,
    "Town": 3,
    "City": 4,
    "Metropolis": 5,
    "Anarchy": 1
}

def get_tier_from_pop(pop: int) -> str:
    if pop >= 10000:
        return "Metropolis"
    elif pop >= 2000:
        return "City"
    elif pop >= 500:
        return "Town"
    elif pop >= 100:
        return "Village"
    elif pop >= 1:
        return "Camp"
    else:
        return "Wilderness"

def scale_species_profile(species_dict, target_pop):
    if not species_dict:
        return {}
    total = sum(species_dict.values())
    if total == 0:
        return {}
    scaled = {}
    for sp, val in species_dict.items():
        scaled[sp] = max(1, int(val * target_pop / total))
    diff = target_pop - sum(scaled.values())
    if diff != 0 and scaled:
        first_sp = list(scaled.keys())[0]
        scaled[first_sp] = max(1, scaled[first_sp] + diff)
    return scaled

def get_default_species_dict(faction, population):
    if not faction:
        return {}
    faction_clean = faction.lstrip('#')
    if faction_clean == "GorgonHorde":
        return {"Gorgons": population}
    elif faction_clean == "CinderClaw":
        return {"CinderClaws": population}
    elif faction_clean == "IronClan":
        return {"IronClans": population}
    else:
        return {f"{faction_clean}_species": population}

class CivilizationExpansionEngine:
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url
        self.cache = {}

    async def get_cell(self, conn, cell_id=None, coord_x=None, coord_y=None):
        if cell_id is not None and cell_id in self.cache:
            return self.cache[cell_id]
        
        for c in self.cache.values():
            if coord_x is not None and coord_y is not None and c["coord_x"] == coord_x and c["coord_y"] == coord_y:
                return c

        if cell_id is not None:
            row = await conn.fetchrow(
                """
                SELECT cell_id, coord_x, coord_y, active_chaos_tag, flora_biomass_data, fauna_population_data, civilization_profile
                FROM global_simulation_cells WHERE cell_id = $1;
                """, cell_id
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT cell_id, coord_x, coord_y, active_chaos_tag, flora_biomass_data, fauna_population_data, civilization_profile
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
            "is_dirty": False
        }
        self.cache[cell["cell_id"]] = cell
        return cell

    async def auto_seed_if_needed(self, conn):
        """
        Seeds the database with three starting settlements if the map is empty of faction cells.
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

        # Coordinates for starting cities
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
                "security": 0.5
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
                "security": 0.5
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
                "security": 0.5
            })
        ]

        for x, y, profile in seeds:
            # Ensure local biomass is maximum so they don't starve on first tick
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
        Runs the full asynchronous civilization expansion, consumption, and reactor safety cycle.
        """
        logger.info("Connecting to database...")
        conn = await asyncpg.connect(self.db_url)
        try:
            # 1. Seeding check
            async with conn.transaction():
                await self.auto_seed_if_needed(conn)

            # 2. Daily cycle calculations
            async with conn.transaction():
                logger.info("Fetching all faction cells...")
                aligned_rows = await conn.fetch(
                    """
                    SELECT cell_id FROM global_simulation_cells
                    WHERE (civilization_profile->>'faction' IS NOT NULL AND civilization_profile->>'faction' != '#Independent')
                       OR (civilization_profile->>'controlling_faction_id' IS NOT NULL);
                    """
                )
                
                aligned_ids = [row["cell_id"] for row in aligned_rows]
                logger.info(f"Processing cycles for {len(aligned_ids)} aligned cells...")

                # Group cells by faction to compute doctrine
                faction_cells = {}
                for cell_id in aligned_ids:
                    cell = await self.get_cell(conn, cell_id=cell_id)
                    if not cell:
                        continue
                    profile = cell["civilization_profile"]
                    faction = profile.get("faction") or profile.get("controlling_faction_id")
                    if not faction or faction == "#Independent":
                        continue
                    if faction not in faction_cells:
                        faction_cells[faction] = []
                    faction_cells[faction].append(cell)

                # Calculate doctrines
                faction_doctrines = {}
                faction_donations = {}
                faction_emergency_cells = {}

                for faction, cells in faction_cells.items():
                    non_wilderness = [c for c in cells if c["civilization_profile"].get("tier", "Wilderness") != "Wilderness"]
                    if not non_wilderness:
                        faction_doctrines[faction] = "NORMAL"
                        continue
                    
                    emergencies = [c for c in non_wilderness if c["civilization_profile"].get("tier") in ["Refugee_Camp", "State_of_Emergency"]]
                    ratio = len(emergencies) / len(non_wilderness)
                    
                    if ratio > 0.20:
                        faction_doctrines[faction] = "REPAIR"
                        faction_emergency_cells[faction] = emergencies
                        faction_donations[faction] = 0.0
                        logger.info(f"Faction {faction} doctrine is REPAIR (Ratio: {ratio:.2%})")
                    else:
                        faction_doctrines[faction] = "NORMAL"
                        logger.info(f"Faction {faction} doctrine is NORMAL (Ratio: {ratio:.2%})")

                # Loop 1 - Pass A: Resource Harvest
                for cell_id in aligned_ids:
                    cell = await self.get_cell(conn, cell_id=cell_id)
                    if not cell:
                        continue
                    
                    profile = cell["civilization_profile"]
                    faction = profile.get("faction", profile.get("controlling_faction_id", "#Independent"))
                    
                    if faction == "#Independent" or not faction:
                        continue

                    # Flora Harvesting
                    flora_data = cell["flora_biomass_data"]
                    biomass = float(flora_data.get("biomass_volume", flora_data.get("biomass_index", 0.0) * 100.0))
                    
                    harvested = biomass * 0.25
                    flora_data["biomass_volume"] = max(0.0, biomass - harvested)
                    cell["is_dirty"] = True

                    available = harvested
                    # Donation logic
                    if faction_doctrines.get(faction) == "REPAIR":
                        tier = profile.get("tier", "Camp")
                        # Healthy if not Refugee_Camp, State_of_Emergency, or Wilderness
                        if tier not in ["Refugee_Camp", "State_of_Emergency", "Wilderness"]:
                            donated = harvested * 0.50
                            faction_donations[faction] = faction_donations.get(faction, 0.0) + donated
                            available = harvested - donated
                            logger.info(f"Cell {cell_id} ({faction}): Healthy cell donating {donated:.2f} biomass. Available: {available:.2f}")

                    cell["temp_available_biomass"] = available

                # Loop 1 - Pass B: Distribute donations to emergency cells
                for faction, emergencies in faction_emergency_cells.items():
                    donated_total = faction_donations.get(faction, 0.0)
                    if emergencies and donated_total > 0:
                        donation_per_cell = donated_total / len(emergencies)
                        for cell in emergencies:
                            cell["temp_available_biomass"] = cell.get("temp_available_biomass", 0.0) + donation_per_cell
                            logger.info(f"Cell {cell['cell_id']} ({faction}): Emergency cell receiving {donation_per_cell:.2f} donated biomass.")

                # Loop 1 - Pass C: Metabolic consumption, Insurgency, and Reactor Checks
                for cell_id in aligned_ids:
                    cell = await self.get_cell(conn, cell_id=cell_id)
                    if not cell:
                        continue
                    
                    profile = cell["civilization_profile"]
                    faction = profile.get("faction", profile.get("controlling_faction_id", "#Independent"))
                    
                    if faction == "#Independent" or not faction:
                        continue

                    # Rebel Insurgency Decay/Growth Loop
                    rebel_block = profile.get("rebel_insurgency")
                    if rebel_block:
                        happiness = float(profile.get("happiness", 0.5))
                        security = float(profile.get("security", 0.5))
                        fervor = float(rebel_block.get("fervor", 5.0))
                        
                        if happiness > 0.60 and security > 0.60:
                            fervor -= 0.5
                        elif happiness < 0.30 or security < 0.30:
                            fervor += 1.0
                            
                        if fervor <= 0.0:
                            profile.pop("rebel_insurgency", None)
                            logger.info(f"Cell {cell_id}: Rebel insurgency faded historically.")
                        elif fervor >= 10.0:
                            rebel_faction = rebel_block["faction"]
                            logger.info(f"UPRISING in cell {cell_id}! Reverting to rebel faction {rebel_faction}")
                            
                            # Overwrite faction alignment back to rebel faction tag
                            faction = rebel_faction
                            profile["faction"] = rebel_faction
                            profile["controlling_faction_id"] = rebel_faction if rebel_faction != "#Independent" else None
                            
                            # Reduce infrastructure tier by 1
                            tier_order = ["Wilderness", "Camp", "Village", "Town", "City", "Metropolis"]
                            current_tier = profile.get("tier", "Camp")
                            if current_tier in ["Refugee_Camp", "State_of_Emergency"]:
                                new_tier = "Wilderness" if current_tier == "Refugee_Camp" else "Camp"
                            else:
                                try:
                                    idx = tier_order.index(current_tier)
                                    new_tier = tier_order[max(0, idx - 1)]
                                except ValueError:
                                    new_tier = "Camp"
                            
                            profile["tier"] = new_tier
                            if new_tier == "Wilderness":
                                profile["has_settlement"] = False
                                profile["population"] = 0
                                faction = "#Independent"
                                profile["faction"] = "#Independent"
                                profile["controlling_faction_id"] = None
                                profile.pop("species", None)
                                
                            profile["happiness"] = 0.50
                            profile.pop("rebel_insurgency", None)
                            cell["is_dirty"] = True
                        else:
                            rebel_block["fervor"] = fervor
                            profile["rebel_insurgency"] = rebel_block
                            cell["is_dirty"] = True

                    # Skip metabolism if cell became Wilderness due to uprising
                    if profile.get("tier", "Wilderness") == "Wilderness" or faction == "#Independent":
                        continue

                    population = int(profile.get("population", 0))
                    reactors = int(profile.get("reactors", 0))
                    shards = int(profile.get("dragonstone_shards", 0))
                    
                    consumption = population * 0.05
                    available_biomass = cell.get("temp_available_biomass", 0.0)

                    if available_biomass > consumption:
                        # Growth
                        new_pop = int(population * 1.02)
                        if new_pop == population and population > 0:
                            new_pop = population + 1
                        new_tier = get_tier_from_pop(new_pop)
                        logger.info(f"Cell {cell_id} ({faction}): Available {available_biomass:.2f} > Consumption {consumption:.2f}. Growth {population} -> {new_pop}. Tier: {new_tier}")
                    else:
                        # Starvation
                        new_pop = int(population * 0.90)
                        if new_pop < 50:
                            new_tier = "Refugee_Camp"
                        else:
                            new_tier = "State_of_Emergency"
                        logger.info(f"Cell {cell_id} ({faction}): Available {available_biomass:.2f} <= Consumption {consumption:.2f}. Starvation {population} -> {new_pop}. Tier: {new_tier}")

                    if new_pop <= 0:
                        new_pop = 0
                        new_tier = "Wilderness"
                        faction = "#Independent"
                        profile["has_settlement"] = False
                        profile.pop("species", None)
                        profile.pop("rebel_insurgency", None)
                    else:
                        profile["has_settlement"] = True

                    profile["population"] = new_pop
                    profile["tier"] = new_tier
                    profile["faction"] = faction
                    profile["controlling_faction_id"] = faction if faction != "#Independent" else None

                    # If species demographic is defined, scale it to match new population
                    if "species" in profile and new_pop > 0:
                        profile["species"] = scale_species_profile(profile["species"], new_pop)

                    # Reactor Blowout Stability Checks
                    if reactors > 0 and faction != "#Independent":
                        shards_to_deduct = reactors
                        profile["dragonstone_shards"] = max(0, shards - shards_to_deduct)
                        
                        for _ in range(reactors):
                            active_tag = cell["active_chaos_tag"]
                            if active_tag == "#StableReality" or not active_tag:
                                failure_rate = 0.02
                            else:
                                failure_rate = 0.35
                            
                            if random.random() < failure_rate:
                                profile["reactors"] = max(0, profile["reactors"] - 1)
                                cell["active_chaos_tag"] = "#MagicalRadiation, #StructuralRupture"
                                
                                fauna_data = cell["fauna_population_data"]
                                populations = fauna_data.get("populations", [])
                                found = False
                                for pop in populations:
                                    if pop.get("species") == "wild_abomination":
                                        pop["density"] = float(pop.get("density", 0.0)) + 1.0
                                        found = True
                                        break
                                if not found:
                                    populations.append({"species": "wild_abomination", "density": 1.0})
                                fauna_data["populations"] = populations
                                fauna_data["total_count"] = fauna_data.get("total_count", 0) + 1
                                
                                logger.warning(f"REACTOR BLOWOUT in cell {cell_id}! Reactor destroyed.")
                                break

                # Loop 2: Frontier Sprawl & Border Skirmishes
                expanding_cells = []
                for cell in list(self.cache.values()):
                    profile = cell["civilization_profile"]
                    faction = profile.get("faction", "#Independent")
                    tier = profile.get("tier", "Wilderness")
                    
                    # Cells belonging to a faction in REPAIR doctrine must skip border expansion entirely
                    if faction != "#Independent" and faction_doctrines.get(faction) == "REPAIR":
                        continue
                        
                    if faction != "#Independent" and tier in ["Town", "City", "Metropolis"]:
                        expanding_cells.append(cell)

                logger.info(f"Expanding settlements to process: {len(expanding_cells)}")
                for exp_cell in expanding_cells:
                    cx = exp_cell["coord_x"]
                    cy = exp_cell["coord_y"]
                    exp_faction = exp_cell["civilization_profile"]["faction"]
                    exp_tier = exp_cell["civilization_profile"]["tier"]
                    
                    # Query 8 neighbor cell IDs
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
                        
                        n_profile = neighbor["civilization_profile"]
                        n_faction = n_profile.get("faction", n_profile.get("controlling_faction_id", "#Independent"))
                        if not n_faction:
                            n_faction = "#Independent"

                        if n_faction == "#Independent":
                            # Cleanly annex neighbor as Tier 1 Camp
                            n_profile["faction"] = exp_faction
                            n_profile["controlling_faction_id"] = exp_faction
                            n_profile["population"] = 10
                            n_profile["tier"] = "Camp"
                            n_profile["has_settlement"] = True
                            n_profile["reactors"] = 0
                            n_profile["dragonstone_shards"] = 0
                            n_profile["development_index"] = 0.1
                            n_profile["happiness"] = 0.50
                            n_profile["security"] = 0.50
                            
                            # Species merge (annexing wilderness)
                            attacker_species = exp_cell["civilization_profile"].get("species", {})
                            if not attacker_species:
                                attacker_species = get_default_species_dict(exp_faction, exp_cell["civilization_profile"].get("population", 10))
                            n_profile["species"] = scale_species_profile(attacker_species, 10)
                            
                            neighbor["is_dirty"] = True
                            logger.info(f"Territorial Sprawl: Cell ({cx}, {cy}) [{exp_faction}] annexed wilderness cell ({neighbor['coord_x']}, {neighbor['coord_y']})")
                        
                        elif n_faction != exp_faction:
                            # Rival faction neighbor: Border Friction Skirmish
                            exp_tier_val = TIER_VALUES.get(exp_tier, 0)
                            n_tier = n_profile.get("tier", "Camp")
                            n_tier_val = TIER_VALUES.get(n_tier, 0)
                            
                            # +3 Tier Advantage multiplier if target is in emergency
                            if n_tier in ["Refugee_Camp", "Anarchy", "State_of_Emergency"]:
                                effective_exp_tier_val = exp_tier_val + 3
                                logger.info(f"Exploiting Disaster: Cell ({cx}, {cy}) [{exp_faction}] targets cell ({neighbor['coord_x']}, {neighbor['coord_y']}) [{n_faction}, tier {n_tier}]. +3 advantage applied.")
                            else:
                                effective_exp_tier_val = exp_tier_val
                            
                            if effective_exp_tier_val > n_tier_val:
                                # Attacker wins, flips neighbor's alignment
                                orig_faction = n_faction
                                
                                # Merge demographics
                                target_species = n_profile.get("species", {})
                                attacker_species = exp_cell["civilization_profile"].get("species", {})
                                if not target_species:
                                    target_species = get_default_species_dict(orig_faction, n_profile.get("population", 10))
                                if not attacker_species:
                                    attacker_species = get_default_species_dict(exp_faction, exp_cell["civilization_profile"].get("population", 10))
                                
                                attacker_bring_size = max(10, int(sum(attacker_species.values()) * 0.50))
                                attacker_brings = scale_species_profile(attacker_species, attacker_bring_size)
                                
                                merged_species = dict(target_species)
                                for sp, val in attacker_brings.items():
                                    merged_species[sp] = merged_species.get(sp, 0) + val
                                
                                n_profile["faction"] = exp_faction
                                n_profile["controlling_faction_id"] = exp_faction
                                n_profile["species"] = merged_species
                                n_profile["population"] = sum(merged_species.values())
                                n_profile["happiness"] = 0.50
                                n_profile["security"] = 0.50
                                
                                # Inject rebel insurgency block
                                n_profile["rebel_insurgency"] = {"faction": orig_faction, "fervor": 5.0}
                                
                                neighbor["is_dirty"] = True
                                logger.info(f"Skirmish Win: Cell ({cx}, {cy}) [{exp_faction}] flips cell ({neighbor['coord_x']}, {neighbor['coord_y']}) [{orig_faction}]. Rebel insurgency injected.")
                                
                            elif n_tier_val > effective_exp_tier_val:
                                # Neighbor wins, flips exp cell's alignment
                                orig_faction = exp_faction
                                
                                # Merge demographics
                                target_species = exp_cell["civilization_profile"].get("species", {})
                                attacker_species = n_profile.get("species", {})
                                if not target_species:
                                    target_species = get_default_species_dict(orig_faction, exp_cell["civilization_profile"].get("population", 10))
                                if not attacker_species:
                                    attacker_species = get_default_species_dict(n_faction, n_profile.get("population", 10))
                                
                                attacker_bring_size = max(10, int(sum(attacker_species.values()) * 0.50))
                                attacker_brings = scale_species_profile(attacker_species, attacker_bring_size)
                                
                                merged_species = dict(target_species)
                                for sp, val in attacker_brings.items():
                                    merged_species[sp] = merged_species.get(sp, 0) + val
                                    
                                exp_cell["civilization_profile"]["faction"] = n_faction
                                exp_cell["civilization_profile"]["controlling_faction_id"] = n_faction
                                exp_cell["civilization_profile"]["species"] = merged_species
                                exp_cell["civilization_profile"]["population"] = sum(merged_species.values())
                                exp_cell["civilization_profile"]["happiness"] = 0.50
                                exp_cell["civilization_profile"]["security"] = 0.50
                                
                                # Inject rebel insurgency block
                                exp_cell["civilization_profile"]["rebel_insurgency"] = {"faction": orig_faction, "fervor": 5.0}
                                
                                exp_cell["is_dirty"] = True
                                logger.info(f"Skirmish Defeat: Expanding cell ({cx}, {cy}) [{orig_faction}] flipped by ({neighbor['coord_x']}, {neighbor['coord_y']}) [{n_faction}].")
                                break

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
                            civilization_profile = $4
                        WHERE cell_id = $5;
                        """,
                        cell["active_chaos_tag"],
                        json.dumps(cell["flora_biomass_data"]),
                        json.dumps(cell["fauna_population_data"]),
                        json.dumps(cell["civilization_profile"]),
                        cell["cell_id"]
                    )
                logger.info("Civilization simulation cycle complete and committed.")
                
        except Exception as e:
            logger.error(f"Error running civilization cycle: {e}")
            raise e
        finally:
            await conn.close()

async def main():
    engine = CivilizationExpansionEngine()
    await engine.run_civilization_cycle()

if __name__ == "__main__":
    asyncio.run(main())
