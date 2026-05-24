import os
import json
import asyncio
import logging
import asyncpg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ecology_matrix_engine")

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:PigPig3897!!@localhost:5432/worldsim")

class EcologicalMatrixEngine:
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url

    async def run_ecology_cycle(self):
        """
        Executes the daily biological cycle across the global grid cells.
        Includes flora growth (regeneration), fauna consumption/mutation, and herd migration.
        All steps are run within database transactions for integrity.
        """
        logger.info("Connecting to database to run ecological cycle...")
        
        # Load flora_base_growth_rate from config.json
        flora_base_growth_rate = 1.0
        config_path = "config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    cfg = json.load(f)
                    flora_base_growth_rate = cfg.get("flora_base_growth_rate", 1.0)
                logger.info(f"Loaded flora_base_growth_rate from config.json: {flora_base_growth_rate}")
            except Exception as e:
                logger.error(f"Failed to load config.json in EcologicalMatrixEngine: {e}")
        
        conn = await asyncpg.connect(self.db_url)
        try:
            # Step 1 & 2: Flora Regeneration, Fauna Consumption & Mutation in a single transaction
            async with conn.transaction():
                logger.info("Executing Step 1: Flora Regeneration...")
                # Update biomass_volume inside flora_biomass_data based on moisture, temperature, and chaos tags.
                # Ocean cells (elevation < 0.0) are zeroed out.
                await conn.execute(
                    """
                    UPDATE global_simulation_cells
                    SET flora_biomass_data = jsonb_set(
                        flora_biomass_data,
                        '{biomass_volume}',
                        to_jsonb(GREATEST(0.0, LEAST(100.0,
                            CASE
                                WHEN elevation_meters < 0.0 THEN 0.0
                                ELSE 
                                    COALESCE((flora_biomass_data->>'biomass_volume')::float, (flora_biomass_data->>'biomass_index')::float * 100.0) +
                                    (
                                        CASE 
                                            WHEN active_chaos_tag IN ('#Vita', '#Epicenter_#Vita') THEN 
                                                (GREATEST(0.0, moisture_index::float * (temperature_celsius::float + 15.0) * 0.1) * 10.0) + 15.0
                                            WHEN active_chaos_tag IN ('#Mass', '#Epicenter_#Mass') THEN 
                                                GREATEST(0.0, moisture_index::float * (temperature_celsius::float + 15.0) * 0.1) * 0.05
                                            ELSE 
                                                GREATEST(0.0, moisture_index::float * (temperature_celsius::float + 15.0) * 0.1)
                                        END
                                    ) * $1
                            END
                        )))
                    );
                    """,
                    flora_base_growth_rate
                )

                logger.info("Executing Step 2: Fauna Consumption & Mutation...")
                # Update local flora biomass by decreasing it based on fauna population size (total_count).
                # Also, if the cell's active_chaos_tag is #Flux, increase internal mutation_index by 0.5.
                await conn.execute(
                    """
                    UPDATE global_simulation_cells
                    SET 
                        flora_biomass_data = jsonb_set(
                            flora_biomass_data,
                            '{biomass_volume}',
                            to_jsonb(GREATEST(0.0, 
                                COALESCE((flora_biomass_data->>'biomass_volume')::float, (flora_biomass_data->>'biomass_index')::float * 100.0) - 
                                (COALESCE((fauna_population_data->>'total_count')::float, 0.0) * 0.05)
                            ))
                        ),
                        fauna_population_data = jsonb_set(
                            fauna_population_data,
                            '{mutation_index}',
                            to_jsonb(
                                COALESCE((fauna_population_data->>'mutation_index')::float, 0.0) +
                                CASE 
                                    WHEN active_chaos_tag IN ('#Flux', '#Epicenter_#Flux') THEN 0.5
                                    ELSE 0.0
                                END
                            )
                        );
                    """
                )
                logger.info("Flora regeneration and fauna consumption/mutation bulk updates completed.")

            # Step 3: Spatial Herd Migration Loop
            logger.info("Executing Step 3: Spatial Herd Migration...")
            
            # Query all starving cells: biomass_volume < 20.0 and total_count > 10
            starving_cells = await conn.fetch(
                """
                SELECT cell_id, coord_x, coord_y, flora_biomass_data, fauna_population_data
                FROM global_simulation_cells
                WHERE COALESCE((flora_biomass_data->>'biomass_volume')::float, (flora_biomass_data->>'biomass_index')::float * 100.0) < 20.0
                  AND COALESCE((fauna_population_data->>'total_count')::int, 0) > 10;
                """
            )
            
            logger.info(f"Found {len(starving_cells)} starving cells. Processing migration...")
            
            migrations_executed = 0
            for cell in starving_cells:
                cell_id = cell["cell_id"]
                cx = cell["coord_x"]
                cy = cell["coord_y"]
                
                # Load origin fauna data
                fauna_data = json.loads(cell["fauna_population_data"])
                total_count = fauna_data.get("total_count", 0)
                
                # Calculate moved population (35%)
                moved_count = int(total_count * 0.35)
                if moved_count <= 0:
                    continue
                
                # Query 8 immediate neighbors to find the one with highest flora biomass
                neighbors = await conn.fetch(
                    """
                    SELECT cell_id, coord_x, coord_y, flora_biomass_data, fauna_population_data,
                           COALESCE((flora_biomass_data->>'biomass_volume')::float, (flora_biomass_data->>'biomass_index')::float * 100.0) AS biomass_volume
                    FROM global_simulation_cells
                    WHERE coord_x BETWEEN $1 - 1 AND $1 + 1
                      AND coord_y BETWEEN $2 - 1 AND $2 + 1
                      AND NOT (coord_x = $1 AND coord_y = $2)
                    ORDER BY biomass_volume DESC
                    LIMIT 1;
                    """,
                    cx, cy
                )
                
                if not neighbors:
                    continue
                
                best_neighbor = neighbors[0]
                dest_cell_id = best_neighbor["cell_id"]
                dest_fauna_data = json.loads(best_neighbor["fauna_population_data"])
                
                # Perform migration calculation
                # Origin update:
                fauna_data["total_count"] = total_count - moved_count
                
                # Proportional distribution of migrated species
                origin_populations = fauna_data.get("populations", [])
                dest_populations = dest_fauna_data.get("populations", [])
                
                for pop in origin_populations:
                    species_name = pop.get("species")
                    orig_density = float(pop.get("density", 0.0))
                    moved_density = orig_density * 0.35
                    pop["density"] = orig_density * 0.65
                    
                    # Find matching species in destination
                    found = False
                    for dest_pop in dest_populations:
                        if dest_pop.get("species") == species_name:
                            dest_pop["density"] = float(dest_pop.get("density", 0.0)) + moved_density
                            found = True
                            break
                    if not found:
                        dest_populations.append({
                            "species": species_name,
                            "density": moved_density
                        })
                
                dest_fauna_data["total_count"] = dest_fauna_data.get("total_count", 0) + moved_count
                dest_fauna_data["populations"] = dest_populations
                
                # Execute simultaneous UPDATE statements inside a transaction
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE global_simulation_cells SET fauna_population_data = $1 WHERE cell_id = $2;",
                        json.dumps(fauna_data), cell_id
                    )
                    await conn.execute(
                        "UPDATE global_simulation_cells SET fauna_population_data = $1 WHERE cell_id = $2;",
                        json.dumps(dest_fauna_data), dest_cell_id
                    )
                
                migrations_executed += 1
                
            logger.info(f"Herd migration complete. Executed {migrations_executed} migration updates.")

            # --- OVERHAUL: STEP 4: SENTIENT RACE GROWTH & ADAPTATION ---
            logger.info("Executing Step 4: Sentient Race Growth & Adaptation...")
            
            # Query races registry
            races_rows = await conn.fetch(
                """
                SELECT race_name, temp_preference_min, temp_preference_max, 
                       moisture_preference_min, moisture_preference_max, 
                       reproduction_rate, food_consumption_rate 
                FROM registry_races;
                """
            )
            races_map = {
                r["race_name"]: {
                    "temp_min": float(r["temp_preference_min"]),
                    "temp_max": float(r["temp_preference_max"]),
                    "moist_min": float(r["moisture_preference_min"]),
                    "moist_max": float(r["moisture_preference_max"]),
                    "reproduction": float(r["reproduction_rate"]),
                    "consumption": float(r["food_consumption_rate"])
                }
                for r in races_rows
            }
            
            # Query all settlement cells
            settlement_cells = await conn.fetch(
                """
                SELECT cell_id, temperature_celsius::float AS temperature_celsius, 
                       moisture_index::float AS moisture_index, civilization_profile
                FROM global_simulation_cells
                WHERE civilization_profile->>'tier' IS NOT NULL 
                  AND civilization_profile->>'tier' != 'Wilderness';
                """
            )
            
            logger.info(f"Processing race demographics for {len(settlement_cells)} settlements...")
            
            for cell_row in settlement_cells:
                cell_id = cell_row["cell_id"]
                cell_temp = cell_row["temperature_celsius"]
                cell_moist = cell_row["moisture_index"]
                
                civ_profile = json.loads(cell_row["civilization_profile"]) if isinstance(cell_row["civilization_profile"], str) else cell_row["civilization_profile"]
                if not civ_profile:
                    continue
                    
                species_dict = civ_profile.get("species")
                if not species_dict or not isinstance(species_dict, dict):
                    continue
                    
                updated_species = {}
                total_pop = 0
                
                for race_name, pop_val in species_dict.items():
                    old_pop = int(pop_val)
                    if old_pop <= 0:
                        continue
                        
                    race_info = races_map.get(race_name)
                    if race_info:
                        pref_temp = (race_info["temp_min"] + race_info["temp_max"]) / 2.0
                        pref_moist = (race_info["moist_min"] + race_info["moist_max"]) / 2.0
                        
                        # Quadratic climate tax
                        dist_tax = 0.05 * (((cell_temp - pref_temp) ** 2) + 100.0 * ((cell_moist - pref_moist) ** 2))
                        dist_tax = max(0.0, min(10.0, dist_tax))
                        
                        # Calculate growth/decline rate
                        growth_rate = (race_info["reproduction"] * 0.02) - (dist_tax * 0.01)
                        new_pop = max(1, int(old_pop * (1.0 + growth_rate)))
                    else:
                        new_pop = old_pop
                        
                    updated_species[race_name] = new_pop
                    total_pop += new_pop
                    
                if updated_species:
                    civ_profile["species"] = updated_species
                    civ_profile["population"] = total_pop
                    
                    # Update cell in database
                    await conn.execute(
                        """
                        UPDATE global_simulation_cells
                        SET civilization_profile = $1
                        WHERE cell_id = $2;
                        """,
                        json.dumps(civ_profile), cell_id
                    )
            
            logger.info("Sentient race demographics update complete.")

        except Exception as e:
            logger.error(f"Error running ecological cycle: {e}")
            raise e
        finally:
            await conn.close()

async def main():
    engine = EcologicalMatrixEngine()
    await engine.run_ecology_cycle()

if __name__ == "__main__":
    asyncio.run(main())
