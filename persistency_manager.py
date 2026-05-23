import os
import json
import logging
import asyncpg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("persistency_manager")

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:PigPig3897!!@localhost:5432/worldsim")

async def execute_garbage_collection_sweep(db_url: str = DATABASE_URL):
    """
    Scans the interior_persistency_deltas table and iterates through the dropped_floor_items array.
    Decrements the "decay_ticks" of each item by 1.
    If decay_ticks reaches 0, removes the item completely.
    """
    logger.info("Executing hourly scavenger sweep garbage collection...")
    conn = await asyncpg.connect(db_url)
    try:
        async with conn.transaction():
            rows = await conn.fetch(
                "SELECT interior_instance_id, dropped_floor_items FROM interior_persistency_deltas;"
            )
            
            for row in rows:
                instance_id = row["interior_instance_id"]
                items_data = row["dropped_floor_items"]
                
                if isinstance(items_data, str):
                    try:
                        items = json.loads(items_data)
                    except:
                        items = []
                else:
                    items = items_data or []
                    
                if not isinstance(items, list):
                    continue
                    
                updated_items = []
                changed = False
                
                for item in items:
                    if isinstance(item, dict) and "decay_ticks" in item:
                        # Decrement tick count
                        try:
                            ticks = int(item["decay_ticks"]) - 1
                        except (ValueError, TypeError):
                            ticks = 72
                        
                        if ticks <= 0:
                            logger.info(f"Instance '{instance_id}': Item decayed completely and was removed: {item}")
                            changed = True
                            continue # Do not add to updated_items (removes it)
                        else:
                            item["decay_ticks"] = ticks
                            changed = True
                    updated_items.append(item)
                    
                if changed:
                    await conn.execute(
                        """
                        UPDATE interior_persistency_deltas
                        SET dropped_floor_items = $1
                        WHERE interior_instance_id = $2;
                        """,
                        json.dumps(updated_items),
                        instance_id
                    )
            logger.info("Scavenger sweep garbage collection complete.")
    except Exception as e:
        logger.error(f"Error during scavenger sweep garbage collection: {e}")
        raise e
    finally:
        await conn.close()
