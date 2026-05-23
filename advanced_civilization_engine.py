import os
import json
import logging
import random
from typing import Dict, List, Any, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("advanced_civilization_engine")

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


def calculate_transit_risk(travel_types: List[str], security: float, wealth: float, biomass: float) -> Tuple[float, float, float]:
    """
    Computes transit risk loss percentage based on travel unlocks and cell security.
    Returns: loss_percentage (float), wealth_lost (float), biomass_lost (float)
    """
    # Determine base risk rate based on travel unlock tiers
    if "Steampunk Airships" in travel_types:
        base_risk = 0.05 # 5% base risk for high-tier airships
    elif "Caravans" in travel_types:
        base_risk = 0.20 # 20% base risk for standard caravans
    else:
        base_risk = 0.20 # fallback default caravans
        
    # Scale risk based on security (security ranges from 0.0 to 1.0)
    loss_pct = (1.0 - security) * base_risk
    
    wealth_lost = wealth * loss_pct
    biomass_lost = biomass * loss_pct
    
    return loss_pct, wealth_lost, biomass_lost


def resolve_armed_conflict(force_a: Dict[str, Any], force_b: Dict[str, Any]) -> List[str]:
    """
    Simulates a tick-based contested conflict resolution between two armed forces.
    Each tick, executes a contested Attack vs. Defense d20 roll supplemented by attributes.
    Deducts 1 action token/charge per tick. Continues until one force is neutralized (HP <= 0) or retreats (tokens run out).
    Returns a log list of combat events.
    """
    combat_log = []
    combat_log.append(f"CONFLICT START: {force_a['name']} (HP: {force_a['hp']}) vs {force_b['name']} (HP: {force_b['hp']})")
    
    tick = 1
    while force_a["hp"] > 0 and force_b["hp"] > 0 and force_a["action_tokens"] > 0 and force_b["action_tokens"] > 0:
        roll_a = random.randint(1, 20) + force_a["attack_attribute"]
        roll_b = random.randint(1, 20) + force_b["defense_attribute"]
        
        # Deduct 1 token from both forces
        force_a["action_tokens"] -= 1
        force_b["action_tokens"] -= 1
        
        if roll_a > roll_b:
            damage = roll_a - roll_b
            force_b["hp"] = max(0, force_b["hp"] - damage)
            combat_log.append(f"Tick {tick}: {force_a['name']} wins contested check ({roll_a} vs {roll_b}) dealing {damage} DMG to {force_b['name']}. ({force_b['name']} HP: {force_b['hp']})")
        elif roll_b > roll_a:
            damage = roll_b - roll_a
            force_a["hp"] = max(0, force_a["hp"] - damage)
            combat_log.append(f"Tick {tick}: {force_b['name']} wins contested check ({roll_b} vs {roll_a}) dealing {damage} DMG to {force_a['name']}. ({force_a['name']} HP: {force_a['hp']})")
        else:
            combat_log.append(f"Tick {tick}: Contested check tied ({roll_a} vs {roll_b}). No damage dealt.")
            
        tick += 1
        
    if force_a["hp"] <= 0:
        combat_log.append(f"CONFLICT RESOLVED: {force_a['name']} was neutralized! {force_b['name']} wins.")
    elif force_b["hp"] <= 0:
        combat_log.append(f"CONFLICT RESOLVED: {force_b['name']} was neutralized! {force_a['name']} wins.")
    else:
        combat_log.append(f"CONFLICT RESOLVED: Action tokens exhausted. Both forces retreated. ({force_a['name']} HP: {force_a['hp']}, {force_b['name']} HP: {force_b['hp']})")
        
    return combat_log


def generate_paragon_agent(role: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dynamically generates a new Paragon agent with traits and goals drawn from
    the paragon_psychology_pool in config.json.
    """
    psych_pool = config.get("paragon_psychology_pool", {})
    names = psych_pool.get("names", ["Viceroy Roderick", "Captain Steelclad", "Eldest Ignis", "General Vraka"])
    traits = psych_pool.get("traits", ["calculating", "greedy", "dutiful", "vigilant", "narcissistic", "zealot"])
    goals = psych_pool.get("personal_goals", ["Maintain stability", "Expand treasury", "Defend boundaries"])
    
    name = random.choice(names) if names else "Unnamed Paragon"
    agent_traits = random.sample(traits, min(2, len(traits))) if traits else []
    agent_goals = random.sample(goals, min(2, len(goals))) if goals else []
    
    return {
        "name": name,
        "role": role,
        "is_criminal": False,
        "personal_goals": agent_goals,
        "traits": agent_traits
    }


class FactionLogisticsEngine:
    """
    Overhauled Gameplay Engine implementing the reactive 9-layer simulation loop.
    Manages resources, transit risks, airship fuel, cartels, paragons, and skirmishes.
    """
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.cache = {}
        
    async def get_cell(self, conn, cell_id):
        if cell_id in self.cache:
            return self.cache[cell_id]
            
        row = await conn.fetchrow(
            """
            SELECT cell_id, coord_x, coord_y, active_chaos_tag, flora_biomass_data, fauna_population_data, civilization_profile
            FROM global_simulation_cells WHERE cell_id = $1;
            """, cell_id
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
        
        # Initialize default advanced logistics parameters in profile
        profile = cell["civilization_profile"]
        
        # Ensure treasury is a JSON dictionary
        treasury = profile.setdefault("treasury", 100.0)
        if isinstance(treasury, (int, float)):
            profile["treasury"] = {"wealth": float(treasury)}
            
        profile.setdefault("unlocked_travel_types", ["Caravans"])
        profile.setdefault("crime_rate", 0.0)
        profile.setdefault("cartel_saturation", 0.0)
        profile.setdefault("cartel_roster_size", 5)
        profile.setdefault("active_airships", 0)
        profile.setdefault("morbidity_and_trauma_matrix", {"narcotic_addiction": 0.0, "alcohol_dependence": 0.0})
        profile.setdefault("paragons", [])
        
        self.cache[cell_id] = cell
        return cell

    async def execute_simulation_turn(self):
        """
        Executes the strictly reactive 9-layer simulation cycle across all aligned faction cells.
        """
        # Load configuration dynamically
        config_path = "config.json"
        config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load config.json in FactionLogisticsEngine: {e}")

        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                # Fetch all aligned faction cells
                rows = await conn.fetch(
                    """
                    SELECT cell_id FROM global_simulation_cells
                    WHERE (civilization_profile->>'faction' IS NOT NULL AND civilization_profile->>'faction' != '#Independent')
                       OR (civilization_profile->>'controlling_faction_id' IS NOT NULL);
                    """
                )
                aligned_ids = [r["cell_id"] for r in rows]
                logger.info(f"FactionLogisticsEngine: Processing 9-layer simulation for {len(aligned_ids)} settlements...")
                
                # Load all aligned cells into memory cache
                for cid in aligned_ids:
                    await self.get_cell(conn, cid)
                    
                # Group cells by faction to compute doctrine
                faction_cells = {}
                for cell in self.cache.values():
                    profile = cell["civilization_profile"]
                    faction = profile.get("faction") or profile.get("controlling_faction_id")
                    if not faction or faction == "#Independent":
                        continue
                    faction_cells.setdefault(faction, []).append(cell)
                    
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
                    else:
                        faction_doctrines[faction] = "NORMAL"

                # ----------------------------------------------------
                # LAYER 1: RESOURCE HARVEST & GENERATION
                # ----------------------------------------------------
                for cell in self.cache.values():
                    profile = cell["civilization_profile"]
                    tier = profile.get("tier", "Wilderness")
                    
                    # 1. Base Raw Wealth Generation
                    if tier == "Metropolis":
                        raw_wealth = 150.0
                    elif tier == "City":
                        raw_wealth = 75.0
                    elif tier == "Town":
                        raw_wealth = 35.0
                    elif tier == "Village":
                        raw_wealth = 15.0
                    elif tier == "Camp":
                        raw_wealth = 5.0
                    elif tier == "State_of_Emergency":
                        raw_wealth = 3.0
                    elif tier == "Refugee_Camp":
                        raw_wealth = 2.0
                    else:
                        raw_wealth = 0.0
                        
                    # 2. Raw Biomass Flora Harvesting
                    flora_data = cell["flora_biomass_data"]
                    biomass = float(flora_data.get("biomass_volume", flora_data.get("biomass_index", 0.0) * 100.0))
                    raw_biomass = biomass * 0.25
                    flora_data["biomass_volume"] = max(0.0, biomass - raw_biomass)
                    cell["is_dirty"] = True
                    
                    cell["temp_harvested_wealth"] = raw_wealth
                    cell["temp_harvested_biomass"] = raw_biomass

                # ----------------------------------------------------
                # LAYER 2: TRANSIT & LOGISTICS
                # ----------------------------------------------------
                for cell in self.cache.values():
                    profile = cell["civilization_profile"]
                    faction = profile.get("faction", "#Independent")
                    
                    travel_types = profile.get("unlocked_travel_types", ["Caravans"])
                    security = float(profile.get("security", 0.5))
                    raw_w = cell["temp_harvested_wealth"]
                    raw_b = cell["temp_harvested_biomass"]
                    
                    # Run transit loss calculation
                    loss_pct, w_lost, b_lost = calculate_transit_risk(travel_types, security, raw_w, raw_b)
                    
                    net_w = max(0.0, raw_w - w_lost)
                    net_b = max(0.0, raw_b - b_lost)
                    
                    # Store net resources into the dictionary
                    profile["treasury"]["wealth"] += net_w
                    cell["is_dirty"] = True
                    
                    # Donation logic (from net harvested biomass)
                    available_b = net_b
                    if faction_doctrines.get(faction) == "REPAIR":
                        tier = profile.get("tier", "Camp")
                        if tier not in ["Refugee_Camp", "State_of_Emergency", "Wilderness"]:
                            donated = net_b * 0.50
                            faction_donations[faction] = faction_donations.get(faction, 0.0) + donated
                            available_b = net_b - donated
                            
                    cell["temp_available_biomass"] = available_b

                # Distribute donations to emergency cells
                for faction, emergencies in faction_emergency_cells.items():
                    donated_total = faction_donations.get(faction, 0.0)
                    if emergencies and donated_total > 0:
                        donation_per_cell = donated_total / len(emergencies)
                        for cell in emergencies:
                            cell["temp_available_biomass"] = cell.get("temp_available_biomass", 0.0) + donation_per_cell

                # ----------------------------------------------------
                # DYNAMIC FACTORY & COMMODITIES PRODUCTION
                # ----------------------------------------------------
                economy_registry = config.get("economy_and_production_registry", {})
                for cell in self.cache.values():
                    profile = cell["civilization_profile"]
                    if profile.get("tier", "Wilderness") == "Wilderness":
                        continue
                        
                    cell_tier = profile.get("tier", "Camp")
                    cell_tier_idx = TIER_VALUES.get(cell_tier, 0)
                    
                    for item_name, item_info in economy_registry.items():
                        req_tag = item_info.get("requires_tag")
                        unlock_tier = item_info.get("unlocked_at_tier", "Camp")
                        req_tier_idx = TIER_VALUES.get(unlock_tier, 0)
                        
                        if cell_tier_idx >= req_tier_idx:
                            active_tag = cell.get("active_chaos_tag") or ""
                            tags_list = [t.strip().lower() for t in active_tag.split(",")]
                            if req_tag and req_tag.lower() in tags_list:
                                # Convert up to 25% of available biomass or max 2.0 biomass into refined goods
                                avail_b = cell.get("temp_available_biomass", 0.0)
                                to_convert = min(avail_b * 0.25, 2.0)
                                if to_convert > 0.0:
                                    cell["temp_available_biomass"] = avail_b - to_convert
                                    profile["treasury"][item_name] = profile["treasury"].get(item_name, 0.0) + to_convert
                                    logger.info(f"Production: Cell {cell['cell_id']} converted {to_convert:.2f} biomass to {item_name}.")
                                    cell["is_dirty"] = True

                # ----------------------------------------------------
                # LAYER 3: STOCKPILE ALLOCATION
                # ----------------------------------------------------
                for cell in self.cache.values():
                    profile = cell["civilization_profile"]
                    
                    # 1. Metabolic Consumption
                    population = int(profile.get("population", 0))
                    metabolic_need = population * 0.05
                    available_b = cell["temp_available_biomass"]
                    
                    if available_b >= metabolic_need:
                        # Growth
                        new_pop = int(population * 1.02)
                        if new_pop == population and population > 0:
                            new_pop = population + 1
                        new_tier = get_tier_from_pop(new_pop)
                        cell["unmet_food_demand"] = False
                    else:
                        # Starvation
                        new_pop = int(population * 0.90)
                        if new_pop < 50:
                            new_tier = "Refugee_Camp"
                        else:
                            new_tier = "State_of_Emergency"
                        cell["unmet_food_demand"] = True
                        
                    if new_pop <= 0:
                        new_pop = 0
                        new_tier = "Wilderness"
                        profile["has_settlement"] = False
                        profile.pop("species", None)
                    else:
                        profile["has_settlement"] = True
                        
                    profile["population"] = new_pop
                    profile["tier"] = new_tier
                    if "species" in profile and new_pop > 0:
                        profile["species"] = scale_species_profile(profile["species"], new_pop)
                    cell["is_dirty"] = True
                    
                    # 2. Dragonstone Fuel Consumption (Reactors and Airships)
                    reactors = int(profile.get("reactors", 0))
                    airships = int(profile.get("active_airships", 0))
                    shards = int(profile.get("dragonstone_shards", 0))
                    
                    # Airships require 2 shards of fuel, reactors require 1 shard
                    total_fuel_needed = reactors + (airships * 2)
                    
                    if shards >= total_fuel_needed:
                        profile["dragonstone_shards"] = shards - total_fuel_needed
                        cell["temp_reactors_active"] = reactors
                    else:
                        # Under-fueled conditions
                        remaining_shards = shards
                        # Fuel reactors first
                        fueled_reactors = min(reactors, remaining_shards)
                        remaining_shards -= fueled_reactors
                        
                        # Fuel airships with remaining
                        fueled_airships = min(airships, remaining_shards // 2)
                        
                        profile["dragonstone_shards"] = 0
                        cell["temp_reactors_active"] = fueled_reactors
                        
                        # Ground un-fueled airships
                        if fueled_airships < airships:
                            logger.warning(f"Cell {cell['cell_id']}: Grounding airships due to fuel shortage.")
                            profile["active_airships"] = fueled_airships
                            if "Steampunk Airships" in profile.get("unlocked_travel_types", []):
                                profile["unlocked_travel_types"].remove("Steampunk Airships")
                                
                    # 3. Security Upkeep Investment
                    wealth = profile["treasury"]["wealth"]
                    if wealth > 50.0:
                        surplus = wealth - 50.0
                        upkeep_spent = min(surplus, 20.0)
                        profile["treasury"]["wealth"] = wealth - upkeep_spent
                        profile["security"] = min(1.0, float(profile.get("security", 0.5)) + upkeep_spent * 0.02)

                # ----------------------------------------------------
                # LAYER 4: PERSISTENT CARTEL LAYER
                # ----------------------------------------------------
                for cell in self.cache.values():
                    profile = cell["civilization_profile"]
                    if profile.get("tier", "Wilderness") == "Wilderness":
                        continue
                        
                    happiness = float(profile.get("happiness", 0.5))
                    unmet_food = cell.get("unmet_food_demand", False)
                    
                    # Cartel smuggles if demand is unmet or happiness drops below 40%
                    if unmet_food or happiness < 0.40:
                        # Smuggling boosts happiness
                        profile["happiness"] = min(1.0, happiness + 0.10)
                        
                        # Aggressively spikes morbidity and dependency
                        matrix = profile.setdefault("morbidity_and_trauma_matrix", {"narcotic_addiction": 0.0, "alcohol_dependence": 0.0})
                        matrix["narcotic_addiction"] = min(1.0, matrix.get("narcotic_addiction", 0.0) + 0.15)
                        matrix["alcohol_dependence"] = min(1.0, matrix.get("alcohol_dependence", 0.0) + 0.10)
                        
                        # Aggressively spikes crime rate
                        profile["crime_rate"] = min(1.0, float(profile.get("crime_rate", 0.0)) + 0.12)
                        cell["is_dirty"] = True

                # ----------------------------------------------------
                # LAYER 5: POLITICAL INFILTRATION
                # ----------------------------------------------------
                for cell in self.cache.values():
                    profile = cell["civilization_profile"]
                    if profile.get("tier", "Wilderness") == "Wilderness":
                        continue
                        
                    crime = float(profile.get("crime_rate", 0.0))
                    saturation = float(profile.get("cartel_saturation", 0.0))
                    
                    if crime >= 0.90 or saturation >= 0.90:
                        # Infiltrate a ruling paragon agent
                        paragons = profile.get("paragons", [])
                        if not paragons:
                            # Create a default paragon using config psychologist pool
                            paragons.append(generate_paragon_agent("Ruling Paragon", config))
                            profile["paragons"] = paragons
                            
                        # Pick a paragon and corrupt them
                        paragon = random.choice(paragons)
                        if not paragon.get("is_criminal", False):
                            paragon["is_criminal"] = True
                            paragon["personal_goals"] = [
                                "Protect cartel operations",
                                "Manipulate the treasury",
                                "Stymie security patrols"
                            ]
                            logger.info(f"POLITICAL INFILTRATION: Paragon {paragon['name']} in Cell {cell['cell_id']} has been corrupted by the cartel.")
                            
                        # Drop crime rate slightly (controlled peace under corrupted agent)
                        profile["crime_rate"] = 0.50
                        cell["is_dirty"] = True

                # ----------------------------------------------------
                # LAYER 6: PARAGON DECISION MATRIX
                # ----------------------------------------------------
                for cell in self.cache.values():
                    profile = cell["civilization_profile"]
                    if profile.get("tier", "Wilderness") == "Wilderness":
                        continue
                        
                    security = float(profile.get("security", 0.5))
                    paragons = profile.get("paragons", [])
                    
                    # If security is low, a Guard Captain (or dutiful/tactical agent) funds patrols
                    if security < 0.40:
                        guard_captain = None
                        for p in paragons:
                            if p.get("role") == "Guard Captain" or "dutiful" in p.get("traits", []):
                                if not p.get("is_criminal", False):
                                    guard_captain = p
                                    break
                                    
                        if guard_captain:
                            patrol_cost = 15.0
                            if profile["treasury"]["wealth"] >= patrol_cost:
                                profile["treasury"]["wealth"] -= patrol_cost
                                profile["security"] = min(1.0, security + 0.15)
                                logger.info(f"Paragon Decision Matrix: Guard Captain {guard_captain['name']} allocated {patrol_cost} wealth to fund patrol routes in Cell {cell['cell_id']}.")
                                cell["is_dirty"] = True

                # ----------------------------------------------------
                # LAYER 7: FRONTIER SPRAWL & CONFLICT DETECTION
                # ----------------------------------------------------
                expanding_cells = []
                for cell in list(self.cache.values()):
                    profile = cell["civilization_profile"]
                    faction = profile.get("faction", "#Independent")
                    tier = profile.get("tier", "Wilderness")
                    
                    if faction != "#Independent" and faction_doctrines.get(faction) == "REPAIR":
                        continue
                        
                    if faction != "#Independent" and tier in ["Town", "City", "Metropolis"]:
                        expanding_cells.append(cell)
                        
                skirmishes_to_resolve = [] # list of (cell_a, cell_b)
                
                for exp_cell in expanding_cells:
                    cx = exp_cell["coord_x"]
                    cy = exp_cell["coord_y"]
                    exp_faction = exp_cell["civilization_profile"]["faction"]
                    
                    # Query neighbors
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
                        neighbor = await self.get_cell(conn, n_row["cell_id"])
                        if not neighbor:
                            continue
                            
                        n_profile = neighbor["civilization_profile"]
                        n_faction = n_profile.get("faction", n_profile.get("controlling_faction_id", "#Independent"))
                        if not n_faction:
                            n_faction = "#Independent"
                            
                        if n_faction == "#Independent":
                            # Annex Independent cell as Camp
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
                            
                            # Initialize treasury dict
                            n_profile["treasury"] = {"wealth": 100.0}
                            
                            attacker_species = exp_cell["civilization_profile"].get("species", {})
                            if not attacker_species:
                                attacker_species = get_default_species_dict(exp_faction, exp_cell["civilization_profile"].get("population", 10))
                            n_profile["species"] = scale_species_profile(attacker_species, 10)
                            
                            neighbor["is_dirty"] = True
                            logger.info(f"Territorial Sprawl: Cell ({cx}, {cy}) [{exp_faction}] annexed Independent cell ({neighbor['coord_x']}, {neighbor['coord_y']})")
                        elif n_faction != exp_faction:
                            # Contested Skirmish Detection
                            skirmishes_to_resolve.append((exp_cell, neighbor))

                # ----------------------------------------------------
                # LAYER 8: CONTESTED SKIRMISH RESOLUTION
                # ----------------------------------------------------
                resolved_cells = set()
                for cell_a, cell_b in skirmishes_to_resolve:
                    # Skip if either cell was already involved/flipped in this loop
                    if cell_a["cell_id"] in resolved_cells or cell_b["cell_id"] in resolved_cells:
                        continue
                        
                    profile_a = cell_a["civilization_profile"]
                    profile_b = cell_b["civilization_profile"]
                    
                    faction_a = profile_a["faction"]
                    faction_b = profile_b["faction"]
                    
                    tier_a = profile_a.get("tier", "Camp")
                    tier_b = profile_b.get("tier", "Camp")
                    
                    # Initialize combat forces
                    force_a = {
                        "name": f"{faction_a.lstrip('#')} Vanguard",
                        "attack_attribute": TIER_VALUES.get(tier_a, 1) * 3,
                        "defense_attribute": TIER_VALUES.get(tier_a, 1) * 2,
                        "hp": TIER_VALUES.get(tier_a, 1) * 100,
                        "action_tokens": 5
                    }
                    
                    force_b = {
                        "name": f"{faction_b.lstrip('#')} Garrison",
                        "attack_attribute": TIER_VALUES.get(tier_b, 1) * 2,
                        "defense_attribute": TIER_VALUES.get(tier_b, 1) * 3,
                        "hp": TIER_VALUES.get(tier_b, 1) * 120,
                        "action_tokens": 5
                    }
                    
                    # Resolve armed conflict
                    logs = resolve_armed_conflict(force_a, force_b)
                    for log in logs:
                        logger.info(log)
                        
                    # Apply results
                    if force_a["hp"] <= 0:
                        # Defender wins. Defender inflicts casualty on attacker population
                        loss_size = int(profile_a.get("population", 0) * 0.15)
                        profile_a["population"] = max(0, profile_a.get("population", 0) - loss_size)
                        profile_a["species"] = scale_species_profile(profile_a.get("species", {}), profile_a["population"])
                        
                        resolved_cells.add(cell_a["cell_id"])
                        cell_a["is_dirty"] = True
                        
                    elif force_b["hp"] <= 0:
                        # Attacker wins. Attacker conquers defender cell
                        orig_faction = faction_b
                        target_pop = profile_b.get("population", 10)
                        
                        # Merge demographics
                        target_species = profile_b.get("species", {})
                        attacker_species = profile_a.get("species", {})
                        
                        attacker_brings = scale_species_profile(attacker_species, max(5, int(target_pop * 0.3)))
                        merged_species = dict(target_species)
                        for sp, val in attacker_brings.items():
                            merged_species[sp] = merged_species.get(sp, 0) + val
                            
                        profile_b["faction"] = faction_a
                        profile_b["controlling_faction_id"] = faction_a
                        profile_b["species"] = merged_species
                        profile_b["population"] = sum(merged_species.values())
                        profile_b["happiness"] = 0.50
                        profile_b["security"] = 0.50
                        
                        # Inject rebel insurgency block
                        profile_b["rebel_insurgency"] = {"faction": orig_faction, "fervor": 5.0}
                        
                        resolved_cells.add(cell_b["cell_id"])
                        cell_b["is_dirty"] = True
                    else:
                        # Both forces retreat, minor casualties on both sides
                        loss_a = int(profile_a.get("population", 0) * 0.05)
                        profile_a["population"] = max(0, profile_a.get("population", 0) - loss_a)
                        profile_a["species"] = scale_species_profile(profile_a.get("species", {}), profile_a["population"])
                        
                        loss_b = int(profile_b.get("population", 0) * 0.05)
                        profile_b["population"] = max(0, profile_b.get("population", 0) - loss_b)
                        profile_b["species"] = scale_species_profile(profile_b.get("species", {}), profile_b["population"])
                        
                        resolved_cells.add(cell_a["cell_id"])
                        resolved_cells.add(cell_b["cell_id"])
                        cell_a["is_dirty"] = True
                        cell_b["is_dirty"] = True

                # ----------------------------------------------------
                # LAYER 9: SETTLEMENT SYNCHRONIZATION
                # ----------------------------------------------------
                dirty_cells = [c for c in self.cache.values() if c["is_dirty"]]
                logger.info(f"Saving {len(dirty_cells)} updated advanced cell records to database...")
                for cell in dirty_cells:
                    # Double check reactor failure blowouts on active reactors
                    reactors = cell.get("temp_reactors_active", 0)
                    profile = cell["civilization_profile"]
                    
                    if reactors > 0:
                        for _ in range(reactors):
                            active_tag = cell["active_chaos_tag"]
                            failure_rate = 0.02 if (active_tag == "#StableReality" or not active_tag) else 0.35
                            
                            if random.random() < failure_rate:
                                profile["reactors"] = max(0, int(profile.get("reactors", 0)) - 1)
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
                                logger.warning(f"REACTOR RUIN: Reactor blowout occurred in Cell {cell['cell_id']}.")
                                break
                                
                    # Bulk SQL update
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
                logger.info("Advanced FactionLogisticsEngine cycle completed and committed.")
