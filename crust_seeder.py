import os
import json
import asyncio
import logging
import numpy as np
from opensimplex import OpenSimplex
import asyncpg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("crust_seeder")

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:PigPig3897!!@localhost:5432/worldsim")

# Map Configuration
WIDTH = 300
HEIGHT = 300
TOTAL_CELLS = WIDTH * HEIGHT

# Procedural Seeds
ELEVATION_SEED = 1337
MOISTURE_SEED = 90210

# Initialize Noise Generators
simplex_elevation = OpenSimplex(seed=ELEVATION_SEED)
simplex_moisture = OpenSimplex(seed=MOISTURE_SEED)

def fbm_noise(x: float, y: float, gen: OpenSimplex, octaves: int = 5, lacunarity: float = 2.0, gain: float = 0.5, scale: float = 0.015) -> float:
    """
    Generates Fractal Brownian Motion noise using OpenSimplex.
    Returns value in range [-1.0, 1.0].
    """
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    max_amplitude = 0.0
    
    for _ in range(octaves):
        nx = x * scale * frequency
        ny = y * scale * frequency
        total += gen.noise2(nx, ny) * amplitude
        max_amplitude += amplitude
        amplitude *= gain
        frequency *= lacunarity
        
    return total / max_amplitude

def get_biome_payloads(elevation: float, temp: float, moisture: float):
    """
    Determines default JSON configurations for cell components based on local climate.
    """
    # Base fallback structures
    flora = {"biomass_index": 0.0, "growth_stage": "dormant", "dominant_species": None}
    fauna = {"populations": [], "total_count": 0, "dominant_species": None}
    civilization = {"controlling_faction_id": None, "development_index": 0.0, "has_settlement": False}
    shadow_war = {"unrest": 0.0, "subversion": 0.0, "corruption": 0.0, "infiltration": 0.0}
    
    # Biome Mapping
    if elevation < 0.0:  # Ocean & Aquatic zones
        if elevation < -500:  # Deep Ocean Abyss
            flora["dominant_species"] = "abyssal_benthos"
            flora["biomass_index"] = 0.01
            fauna["populations"] = [{"species": "abyssal_eel", "density": 0.05}]
            fauna["total_count"] = 50
        else:  # Shallow Coastal Ocean
            flora["dominant_species"] = "kelp_forest"
            flora["biomass_index"] = 0.40
            flora["growth_stage"] = "stable"
            fauna["populations"] = [{"species": "reef_fish", "density": 1.5}, {"species": "sea_otter", "density": 0.2}]
            fauna["total_count"] = 450
            
    elif temp < 0.0:  # Arctic Ice Caps & High-Altitude Glaciers
        flora["dominant_species"] = "snow_algae"
        flora["biomass_index"] = 0.02
        fauna["populations"] = [{"species": "polar_bear", "density": 0.01}]
        fauna["total_count"] = 10
        
    elif temp < 8.0:  # Boreal Forests & Cold Tundra
        if moisture > 0.40:
            flora["dominant_species"] = "pine"
            flora["biomass_index"] = 0.70
            flora["growth_stage"] = "stable"
            fauna["populations"] = [{"species": "boreal_elk", "density": 0.25}, {"species": "lynx", "density": 0.08}]
            fauna["total_count"] = 200
        else:
            flora["dominant_species"] = "alpine_moss"
            flora["biomass_index"] = 0.15
            fauna["populations"] = [{"species": "mountain_goat", "density": 0.12}]
            fauna["total_count"] = 50
            
    elif moisture < 0.15:  # Arid Wastelands / Deserts
        flora["dominant_species"] = "saguaro_cactus"
        flora["biomass_index"] = 0.08
        flora["growth_stage"] = "stunted"
        fauna["populations"] = [{"species": "desert_viper", "density": 0.35}]
        fauna["total_count"] = 100
        shadow_war["unrest"] = 0.08
        
    elif moisture > 0.75:  # Swamps & Tropical Rainforests
        if temp > 22.0:  # Tropical Jungle
            flora["dominant_species"] = "rainforest_fern"
            flora["biomass_index"] = 0.95
            flora["growth_stage"] = "flourishing"
            fauna["populations"] = [{"species": "jaguar", "density": 0.15}, {"species": "tree_frog", "density": 6.2}]
            fauna["total_count"] = 1200
        else:  # Temperate Swamp
            flora["dominant_species"] = "mangrove"
            flora["biomass_index"] = 0.80
            flora["growth_stage"] = "abundant"
            fauna["populations"] = [{"species": "swamp_leech", "density": 2.5}, {"species": "caiman", "density": 0.35}]
            fauna["total_count"] = 50
        shadow_war["corruption"] = 0.12
        
    elif moisture > 0.35:  # Deep Wilderness Forests (Temperate Woodland)
        flora["dominant_species"] = "broadleaf_oak"
        flora["biomass_index"] = 0.85
        flora["growth_stage"] = "flourishing"
        fauna["populations"] = [{"species": "red_deer", "density": 0.75}, {"species": "red_fox", "density": 0.28}]
        fauna["total_count"] = 750
        
    else:  # Temperate Grasslands / Plains
        flora["dominant_species"] = "ryegrass"
        flora["biomass_index"] = 0.45
        flora["growth_stage"] = "stable"
        fauna["populations"] = [{"species": "steppe_gazelle", "density": 1.10}]
        fauna["total_count"] = 400
        civilization["development_index"] = 0.15
        
    return flora, fauna, civilization, shadow_war

async def seed_crust():
    logger.info("Initializing Map Seeding...")
    
    # 1. Generate Base Elevation Grid using fBm Noise (300x300)
    logger.info("Generating organic elevation grid...")
    elevation_grid = np.zeros((WIDTH, HEIGHT))
    for y in range(HEIGHT):
        for x in range(WIDTH):
            noise_val = fbm_noise(x, y, simplex_elevation, octaves=5, scale=0.015)
            # Normalize noise [-1.0, 1.0] -> [-1000m, 3500m]
            norm_val = (noise_val + 1.0) / 2.0
            elevation_grid[x][y] = -1000.0 + (norm_val * 4500.0)

    # 2. Generate Base Moisture Grid using Simplex Noise
    logger.info("Generating moisture grid...")
    moisture_grid = np.zeros((WIDTH, HEIGHT))
    for y in range(HEIGHT):
        for x in range(WIDTH):
            # Scale factor slightly higher for moisture detail
            noise_val = simplex_moisture.noise2(x * 0.02, y * 0.02)
            moisture_grid[x][y] = (noise_val + 1.0) / 2.0

    # 3. Simulate Rain-Shadow Effect
    # When a mountain peak exceeds 2200m, it creates arid conditions downwind (East)
    logger.info("Calculating leeward rain-shadow deserts...")
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if elevation_grid[x][y] > 2200.0:
                # Apply rain shadow to cells immediately East/downwind (e.g. offset +1 and +2)
                for dx in [1, 2]:
                    for dy in [-1, 0, 1]:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                            # Drop humidity to arid levels (e.g., maximum 0.08)
                            moisture_grid[nx][ny] = min(moisture_grid[nx][ny], 0.08)

    # 4. Generate Temperature and Build Record Tuples
    logger.info("Building grid cells and mapping biomes...")
    records = []
    for y in range(HEIGHT):
        # Base sea level temperature (Equator Y=0 is 35C, dropping to -15C at Arctic Y=299)
        base_temp = 35.0 - (y / (HEIGHT - 1)) * 50.0
        
        for x in range(WIDTH):
            elevation = elevation_grid[x][y]
            moisture = moisture_grid[x][y]
            
            # Apply lapse rate: drops by 6.5C for every 1000m of elevation
            temp = base_temp - (elevation / 1000.0) * 6.5
            
            # Map appropriate biomes and components
            flora, fauna, civ, shadow = get_biome_payloads(elevation, temp, moisture)
            
            # Prepare active chaos tag
            active_chaos_tag = None
            if elevation > 3000.0:
                active_chaos_tag = "Cosmic Winds"
            elif temp < -15.0:
                active_chaos_tag = "Eternal Frost"
                
            records.append((
                x,                                 # coord_x
                y,                                 # coord_y
                float(elevation),                  # elevation_meters
                float(temp),                       # temperature_celsius
                float(moisture),                   # moisture_index
                active_chaos_tag,                  # active_chaos_tag
                json.dumps(flora),                 # flora_biomass_data
                json.dumps(fauna),                 # fauna_population_data
                json.dumps(civ),                   # civilization_profile
                json.dumps(shadow)                 # shadow_war_metrics
            ))

    # 5. Bulk Upload to PostgreSQL Database in a Single Transaction
    logger.info("Connecting to database for bulk copy...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        async with conn.transaction():
            # Clear existing data to prevent unique constraint failures
            logger.info("Truncating existing cell records...")
            await conn.execute("TRUNCATE TABLE global_simulation_cells RESTART IDENTITY CASCADE;")
            
            # Copy all 90,000 cells atomically
            logger.info(f"Uploading {len(records)} cell records in bulk copy mode...")
            await conn.copy_records_to_table(
                'global_simulation_cells',
                records=records,
                columns=[
                    'coord_x',
                    'coord_y',
                    'elevation_meters',
                    'temperature_celsius',
                    'moisture_index',
                    'active_chaos_tag',
                    'flora_biomass_data',
                    'fauna_population_data',
                    'civilization_profile',
                    'shadow_war_metrics'
                ]
            )
            logger.info("Bulk upload complete. Database transactions committed.")
    except Exception as e:
        logger.error(f"Bulk upload failed: {e}")
        raise e
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(seed_crust())
