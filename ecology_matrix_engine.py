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
