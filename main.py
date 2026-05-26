import os
import json
import logging
from uuid import UUID
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import asyncpg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simulation_hub")

# Retrieve database connection URI from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:PigPig3897!!@localhost:5432/worldsim")

# Initialize FastAPI App
app = FastAPI(
    title="Planetary Simulation Engine - Core Hub",
    description="Asynchronous local storage backbone and simulation interface.",
    version="1.1.0"
)

# Setup asyncpg custom JSON/JSONB codecs for seamless dictionary and list handling
async def init_db_connection(conn: asyncpg.Connection):
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog"
    )

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing PostgreSQL async connection pool...")
    try:
        app.state.db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=5,
            max_size=20,
            init=init_db_connection
        )
        logger.info("Database connection pool established successfully.")
        
        async with app.state.db_pool.acquire() as conn:
            # 1. Run migrations for player_characters to support personal_chaos_exposure and mutations
            await conn.execute(
                """
                ALTER TABLE player_characters ADD COLUMN IF NOT EXISTS personal_chaos_exposure NUMERIC(5, 2) NOT NULL DEFAULT 0.00;
                ALTER TABLE player_characters ADD COLUMN IF NOT EXISTS mutations JSONB NOT NULL DEFAULT '[]'::jsonb;
                """
            )
            logger.info("Database migrations for player_characters completed.")
            # 3. Create campaign_lore_ledger and vectorized_world_lore dynamically, handling pgvector or fallback
            await conn.execute(
                """
                DO $$
                DECLARE
                    vector_type_exists BOOLEAN;
                    old_table_exists BOOLEAN;
                BEGIN
                    SELECT EXISTS (
                        SELECT 1 FROM pg_type WHERE typname = 'vector'
                    ) INTO vector_type_exists;

                    SELECT EXISTS (
                        SELECT 1 
                        FROM information_schema.columns 
                        WHERE table_name = 'campaign_lore_ledger' AND column_name = 'paragon_name'
                    ) INTO old_table_exists;

                    IF old_table_exists THEN
                        DROP TABLE IF EXISTS campaign_lore_ledger CASCADE;
                    END IF;

                    IF vector_type_exists THEN
                        CREATE TABLE IF NOT EXISTS campaign_lore_ledger (
                            ledger_id SERIAL PRIMARY KEY,
                            associated_cell_id BIGINT REFERENCES global_simulation_cells(cell_id) ON DELETE CASCADE,
                            faction_tag VARCHAR(100) NOT NULL,
                            raw_history_summary TEXT NOT NULL,
                            semantic_lore_embedding vector(1536) NOT NULL,
                            recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                        
                        CREATE TABLE IF NOT EXISTS vectorized_world_lore (
                            lore_id SERIAL PRIMARY KEY,
                            source_file_name VARCHAR(255) NOT NULL,
                            target_faction VARCHAR(100) NOT NULL,
                            geographic_tags VARCHAR(100)[] NOT NULL,
                            raw_lore_text TEXT NOT NULL,
                            lore_embedding vector(1536) NOT NULL,
                            recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                        
                        CREATE INDEX IF NOT EXISTS idx_lore_ledger_hnsw ON campaign_lore_ledger USING hnsw (semantic_lore_embedding vector_cosine_ops);
                        CREATE INDEX IF NOT EXISTS idx_world_lore_hnsw ON vectorized_world_lore USING hnsw (lore_embedding vector_cosine_ops);
                    ELSE
                        CREATE OR REPLACE FUNCTION cosine_similarity(a REAL[], b REAL[])
                        RETURNS REAL AS $body$
                        DECLARE
                            dot_product REAL := 0;
                            norm_a REAL := 0;
                            norm_b REAL := 0;
                            i INT;
                        BEGIN
                            IF array_length(a, 1) IS NULL OR array_length(b, 1) IS NULL THEN
                                RETURN 0;
                            END IF;
                            IF array_length(a, 1) != array_length(b, 1) THEN
                                RETURN 0;
                            END IF;
                            FOR i IN 1..array_length(a, 1) LOOP
                                dot_product := dot_product + (a[i] * b[i]);
                                norm_a := norm_a + (a[i] * a[i]);
                                norm_b := norm_b + (b[i] * b[i]);
                            END LOOP;
                            IF norm_a = 0 OR norm_b = 0 THEN
                                RETURN 0;
                            END IF;
                            RETURN dot_product / (sqrt(norm_a) * sqrt(norm_b));
                        END;
                        $body$ LANGUAGE plpgsql IMMUTABLE;

                        CREATE OR REPLACE FUNCTION cosine_distance(a REAL[], b REAL[])
                        RETURNS REAL AS $body$
                        BEGIN
                            RETURN 1.0 - cosine_similarity(a, b);
                        END;
                        $body$ LANGUAGE plpgsql IMMUTABLE;

                        IF NOT EXISTS (
                            SELECT 1 FROM pg_operator 
                            WHERE oprname = '<=>' 
                              AND oprleft = 'real[]'::regtype 
                              AND oprright = 'real[]'::regtype
                        ) THEN
                            CREATE OPERATOR <=> (
                                leftarg = REAL[],
                                rightarg = REAL[],
                                procedure = cosine_distance
                            );
                        END IF;

                        CREATE TABLE IF NOT EXISTS campaign_lore_ledger (
                            ledger_id SERIAL PRIMARY KEY,
                            associated_cell_id BIGINT REFERENCES global_simulation_cells(cell_id) ON DELETE CASCADE,
                            faction_tag VARCHAR(100) NOT NULL,
                            raw_history_summary TEXT NOT NULL,
                            semantic_lore_embedding REAL[] NOT NULL,
                            recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS vectorized_world_lore (
                            lore_id SERIAL PRIMARY KEY,
                            source_file_name VARCHAR(255) NOT NULL,
                            target_faction VARCHAR(100) NOT NULL,
                            geographic_tags VARCHAR(100)[] NOT NULL,
                            raw_lore_text TEXT NOT NULL,
                            lore_embedding REAL[] NOT NULL,
                            recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE INDEX IF NOT EXISTS idx_lore_ledger_cell_id ON campaign_lore_ledger (associated_cell_id);
                        CREATE INDEX IF NOT EXISTS idx_world_lore_faction ON vectorized_world_lore (target_faction);
                    END IF;
                END;
                $$;
                """
            )
            logger.info("Database migrations for hybrid vector lore tables completed.")

            # 2. Ensure player_saga_stack table exists
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS player_saga_stack (
                    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    character_id UUID NOT NULL REFERENCES player_characters(character_id) ON DELETE CASCADE,
                    target_cell_id BIGINT NOT NULL REFERENCES global_simulation_cells(cell_id) ON DELETE CASCADE,
                    event_type VARCHAR(255) NOT NULL,
                    stat_used VARCHAR(100),
                    roll_result INTEGER,
                    context_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_player_saga_stack_char_recorded 
                ON player_saga_stack (character_id, recorded_at);
                """
            )
            logger.info("Database player_saga_stack table initialized and indexed.")
    except Exception as e:
        logger.error(f"Failed to create database connection pool: {e}")
        raise e

    # Load config.json on startup
    config_path = "config.json"
    default_config = {
        "time_scale_multiplier": 8,
        "fauna_base_reproduction_rate": 2.5,
        "mutation_threshold": 85.0,
        "flora_base_growth_rate": 1.0,
        "economy_and_production_registry": {
            "Medicine": {"requires_tag": "#MedicinalHerb", "unlocked_at_tier": "Town"},
            "Steel": {"requires_tag": "#IronDeposit", "unlocked_at_tier": "City"},
            "AetherFuel": {"requires_tag": "#AetherCrystal", "unlocked_at_tier": "Metropolis"},
            "Lumber": {"requires_tag": "#BorealPine", "unlocked_at_tier": "Hamlet"},
            "Oakwood": {"requires_tag": "#BroadleafOak", "unlocked_at_tier": "Hamlet"},
            "CactusFiber": {"requires_tag": "#SaguaroCactus", "unlocked_at_tier": "Hamlet"},
            "FernExtract": {"requires_tag": "#RainforestFern", "unlocked_at_tier": "Hamlet"},
            "MangroveSap": {"requires_tag": "#BayouMangrove", "unlocked_at_tier": "Hamlet"},
            "AetherElixir": {"requires_tag": "#AethericRootGlow", "unlocked_at_tier": "Town"},
            "AshenPowder": {"requires_tag": "#AshenCinderBloom", "unlocked_at_tier": "Town"},
            "DragonGlass": {"requires_tag": "#DragonstoneVine", "unlocked_at_tier": "City"},
            "SilverInk": {"requires_tag": "#ScholarlySilverLeaf", "unlocked_at_tier": "Town"},
            "JoltBattery": {"requires_tag": "#VoltaicJoltBerry", "unlocked_at_tier": "City"},
            "OzoneCatalyst": {"requires_tag": "#HighAltitudeOzoneFlower", "unlocked_at_tier": "Metropolis"},
            "ElkMeat": {"requires_tag": "#BorealElk", "unlocked_at_tier": "Hamlet"},
            "FoxPelt": {"requires_tag": "#SlyRedFox", "unlocked_at_tier": "Hamlet"},
            "StaticWool": {"requires_tag": "#StaticFleeceSheep", "unlocked_at_tier": "Town"},
            "SkyPirateGuns": {"requires_tag": "#AerostaticCloudHarrier", "unlocked_at_tier": "City"},
            "ClockworkGear": {"requires_tag": "#DeterminedBureaucrats", "unlocked_at_tier": "Town"}
        },
        "paragon_psychology_pool": {
            "first_names": ["Roderick", "Steelclad", "Ignis", "Vraka", "Aurelius", "Malakai", "Kaelen", "Valeria", "Garrick", "Lyra", "Sylas", "Thorne", "Zaria", "Baelor", "Dante", "Helena", "Iris", "Lucius", "Morrigan", "Oberon"],
            "last_names": ["Ironwood", "Stonefist", "Shadowbloom", "Aetherbrand", "Stormbringer", "Grimward", "Sterling", "Holloway", "Blackwood", "Cromwell", "Frost", "Gallowglass", "Vance", "Thorne", "Ashford", "Kingsley", "Wyatt", "Blythe", "Rutherford", "Pendleton"],
            "positive_traits": ["calculated_genius", "indomitable_will", "charismatic_leader", "brilliant_tactician", "saintly_virtue", "steel_resolve", "boundless_empathy"],
            "negative_traits": ["craven_heart", "paranoid_fear", "greed_infected", "melancholy_curse", "bloodlust_frenzy", "hubris_blinded", "frail_constitution"],
            "neutral_traits": ["calculating", "greedy", "dutiful", "vigilant", "narcissistic", "zealot", "ambitious", "stoic", "eccentric", "skeptical", "inquisitive", "pious", "cautious", "frugal", "traditionalist"],
            "personal_goals": ["Maintain stability", "Expand treasury", "Defend boundaries", "Purge heresy", "Amass wealth", "Uncover lost tech", "Establish legacy"]
        }
    }
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                loaded = json.load(f)
            config = default_config.copy()
            # Deep update of dictionary fields if needed, but simple update is fine.
            # Let's merge economy_and_production_registry and paragon_psychology_pool if present.
            for k, v in loaded.items():
                if isinstance(v, dict) and k in config and isinstance(config[k], dict):
                    config[k].update(v)
                else:
                    config[k] = v
            app.state.config = config
            logger.info(f"Loaded config.json: {app.state.config}")
        except Exception as e:
            logger.error(f"Failed to parse config.json: {e}")
            app.state.config = default_config
    else:
        app.state.config = default_config
    
    # Launch ParagonAIDirector background task
    from narrative_quest_engine import ParagonAIDirector
    app.state.ai_director = ParagonAIDirector(app.state.db_pool, app.state.config)
    await app.state.ai_director.start()
    logger.info("ParagonAIDirector background task launched.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Stopping Paragon AI Director...")
    if hasattr(app.state, "ai_director") and app.state.ai_director:
        await app.state.ai_director.stop()
    logger.info("Closing database connection pool...")
    if hasattr(app.state, "db_pool") and app.state.db_pool:
        await app.state.db_pool.close()
        logger.info("Database connection pool closed.")

# Dependency to acquire db pool
async def get_db_pool() -> asyncpg.Pool:
    if not hasattr(app.state, "db_pool") or app.state.db_pool is None:
        raise HTTPException(status_code=500, detail="Database connection pool is uninitialized.")
    return app.state.db_pool

# ============================================================================
# PYDANTIC VALIDATION SCHEMAS
# ============================================================================

class InteriorMutationPayload(BaseModel):
    interior_instance_id: str = Field(..., max_length=255, description="Unique string identifier for the interior layer/sub-instance.")
    container_inventories: Dict[str, Any] = Field(default_factory=dict, description="Inventory mapping for containers within the instance.")
    dropped_floor_items: List[Any] = Field(default_factory=list, description="List of items dropped directly onto the floor.")
    structural_changes: Dict[str, Any] = Field(default_factory=dict, description="Tracking of structural modifications inside the interior.")

class CellUpdatePayload(BaseModel):
    cell_id: int = Field(..., description="ID of the cell being updated.")
    mass_destruction: bool = Field(False, description="Flag indicating mass destruction event.")
    destruction_type: Optional[str] = Field(None, description="Type of destruction, e.g. 'BURNED' or 'CLEAR_CUT'.")

class QuestAssemblePayload(BaseModel):
    character_id: UUID = Field(..., description="UUID of the player character.")
    cell_id: int = Field(..., description="ID of the cell where the quest is taking place.")

class PlayerPoolsUpdatePayload(BaseModel):
    character_id: UUID = Field(..., description="UUID of the character being updated.")
    health: int = Field(..., ge=0, description="Current health pool value.")
    stamina: int = Field(..., ge=0, description="Current stamina pool value.")
    composure: int = Field(..., ge=0, description="Current composure pool value.")
    focus: int = Field(..., ge=0, description="Current focus pool value.")
    trauma: int = Field(..., ge=0, description="Current trauma index value.")
    personal_chaos_exposure: Optional[float] = Field(None, ge=0.0, le=100.0, description="Current personal chaos exposure score.")
    mutations: Optional[List[str]] = Field(None, description="Current physical mutations list.")

class SagaEventPayload(BaseModel):
    character_id: UUID = Field(..., description="UUID of the player character.")
    target_cell_id: int = Field(..., description="Target cell ID on the 300x300 planetary grid.")
    event_type: str = Field(..., max_length=255, description="Type of saga event.")
    stat_used: Optional[str] = Field(None, max_length=100, description="Attribute used in roll check.")
    roll_result: Optional[int] = Field(None, description="Result of the check roll.")
    gameplay_choices: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Log of choices and outcomes.")

class ClashResolvePayload(BaseModel):
    character_id: UUID = Field(..., description="UUID of the character.")
    tactic_a: str = Field(..., description="Tactic chosen by character A (Press, Hold, Maneuver, Trick, Feint, Disengage).")
    tactic_b: str = Field(..., description="Tactic chosen by character B.")
    roll_a: int = Field(..., ge=1, le=20, description="D20 roll of character A.")
    roll_b: int = Field(..., ge=1, le=20, description="D20 roll of character B.")
    opponent_perception: int = Field(..., description="Perception sub-stat of the opponent.")

class ChaosBurnPayload(BaseModel):
    character_id: UUID = Field(..., description="UUID of the character.")
    d100_roll: int = Field(..., ge=1, le=100, description="D100 roll for Channeling the Chaos.")

class PaintCell(BaseModel):
    x: int = Field(..., ge=0, lt=300)
    y: int = Field(..., ge=0, lt=300)

class BrushStrokePlacement(BaseModel):
    cells: List[PaintCell] = Field(..., description="List of cell coordinates painted in this stroke.")
    brush_name: str = Field(..., description="Name of the selected brush.")
    elevation: Optional[float] = Field(None, description="Target elevation_meters if painting climate override.")
    temperature: Optional[float] = Field(None, description="Target temperature_celsius if painting climate override.")
    moisture: Optional[float] = Field(None, description="Target moisture_index if painting climate override.")
    chaos_tag: Optional[str] = Field(None, description="Target active_chaos_tag if painting chaos path.")

class SearchLorePayload(BaseModel):
    query: str
    faction_tag: str
    associated_cell_id: int
    limit: Optional[int] = 3

class FloraItemPayload(BaseModel):
    scientific_name: str
    common_name: str
    temp_preference_min: float
    temp_preference_max: float
    moisture_preference_min: float
    moisture_preference_max: float
    growth_rate_modifier: float
    harvest_resource: Optional[str] = None
    is_fatal_harvest: bool = False
    tags: Optional[List[str]] = None

class FaunaItemPayload(BaseModel):
    scientific_name: str
    common_name: str
    dietary_classification: str
    base_pack_size: int
    reproduction_rate: float
    harvest_resource: Optional[str] = None
    is_fatal_harvest: bool = True
    tags: Optional[List[str]] = None

class FactionItemPayload(BaseModel):
    faction_name: str
    ideology_type: str
    reputation_baseline: int
    faction_type: str = "goverments"
    expansion_level: int = 5
    aggression_level: int = 5
    trade_level: int = 5
    government_type: str = "republic"
    tags: Optional[List[str]] = None
    faction_trait: str = "bonus_trade"

class RaceItemPayload(BaseModel):
    race_name: str
    genus_type: str
    associated_faction_name: Optional[str] = None
    temp_preference_min: float
    temp_preference_max: float
    moisture_preference_min: float
    moisture_preference_max: float
    reproduction_rate: float = 1.0
    food_consumption_rate: float = 1.0

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/api/world-state")
async def get_world_state(pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Returns the master simulation time from the single-row system_clock table.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT current_year, current_day, current_segment FROM system_clock WHERE id = 1;"
        )
        if not row:
            raise HTTPException(status_code=404, detail="System clock state not found.")
        return dict(row)

@app.get("/api/cell/{cell_id}")
async def get_cell(cell_id: int, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Returns the full simulation profile for a specific macro cell by ID.
    Casts elevation, temperature, and moisture to float to prevent Decimal serialization issues.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 
                cell_id, 
                coord_x, 
                coord_y, 
                elevation_meters::float AS elevation_meters, 
                temperature_celsius::float AS temperature_celsius, 
                moisture_index::float AS moisture_index, 
                active_chaos_tag, 
                flora_biomass_data, 
                fauna_population_data, 
                civilization_profile, 
                shadow_war_metrics 
            FROM global_simulation_cells 
            WHERE cell_id = $1;
            """,
            cell_id
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Simulation cell {cell_id} not found.")
        return dict(row)

@app.post("/api/interior/save")
async def save_interior(payload: InteriorMutationPayload, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Saves or updates container inventories, dropped floor items, and structural changes
    for virtual sub-layers inside the interior_persistency_deltas table.
    Automatically injects a "decay_ticks": 72 key to any item or body that does NOT possess a #Permanent tag.
    """
    processed_items = []
    for item in payload.dropped_floor_items:
        if isinstance(item, dict):
            # Check for #Permanent tag across tags, tag field, or any field value
            has_permanent = False
            tags = item.get("tags")
            if isinstance(tags, list):
                if "#Permanent" in tags or "Permanent" in tags:
                    has_permanent = True
            
            tag = item.get("tag")
            if isinstance(tag, str) and ("#Permanent" in tag or "Permanent" in tag):
                has_permanent = True
                
            for k, v in item.items():
                if isinstance(v, str) and "#Permanent" in v:
                    has_permanent = True
            
            # Inject decay_ticks: 72 if not permanent
            if not has_permanent:
                item["decay_ticks"] = 72
        processed_items.append(item)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO interior_persistency_deltas (
                interior_instance_id, 
                container_inventories, 
                dropped_floor_items, 
                structural_changes
            )
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (interior_instance_id) DO UPDATE SET
                container_inventories = EXCLUDED.container_inventories,
                dropped_floor_items = EXCLUDED.dropped_floor_items,
                structural_changes = EXCLUDED.structural_changes
            RETURNING interior_instance_id;
            """,
            payload.interior_instance_id,
            payload.container_inventories,
            processed_items,
            payload.structural_changes
        )
        if not row:
            raise HTTPException(status_code=500, detail="Failed to persist interior mutation changes.")
        return {"status": "success", "interior_instance_id": row["interior_instance_id"]}

@app.post("/api/cell/update")
async def update_cell(payload: CellUpdatePayload, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Updates the macro cell profile.
    If mass_destruction is flag, promotes the event by zeroing flora biomass and appending Scorched_Earth/Deforested tags.
    """
    async with pool.acquire() as conn:
        # Fetch current cell state
        row = await conn.fetchrow(
            "SELECT active_chaos_tag, flora_biomass_data, civilization_profile FROM global_simulation_cells WHERE cell_id = $1;",
            payload.cell_id
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Cell {payload.cell_id} not found.")

        active_tag = row["active_chaos_tag"]
        flora_data = row["flora_biomass_data"]
        civ_profile = row["civilization_profile"]

        if isinstance(flora_data, str):
            flora_data = json.loads(flora_data)
        if isinstance(civ_profile, str):
            civ_profile = json.loads(civ_profile)

        if payload.mass_destruction:
            # Promote mass destruction
            # 1. Zero out biomass
            flora_data["biomass_volume"] = 0.0
            flora_data["biomass_index"] = 0.0
            
            # Determine tag to append
            tag_to_append = "#Scorched_Earth"
            if payload.destruction_type:
                dest_type = payload.destruction_type.upper()
                if "BURN" in dest_type or "FIRE" in dest_type:
                    tag_to_append = "#Scorched_Earth"
                    flora_data["growth_stage"] = "scorched"
                elif "CUT" in dest_type or "CLEAR" in dest_type or "DEFOREST" in dest_type:
                    tag_to_append = "#Deforested"
                    flora_data["growth_stage"] = "deforested"

            # 2. Append tag to active_chaos_tag column list
            if not active_tag or active_tag == "#StableReality":
                new_active_tag = tag_to_append
            else:
                tags_list = [t.strip() for t in active_tag.split(",")]
                if tag_to_append not in tags_list:
                    tags_list.append(tag_to_append)
                new_active_tag = ", ".join(tags_list)

            # 3. Append tag to flora biomass and civ profile tags just in case
            for d in [flora_data, civ_profile]:
                tags_arr = d.get("tags", [])
                if not isinstance(tags_arr, list):
                    tags_arr = []
                if tag_to_append not in tags_arr:
                    tags_arr.append(tag_to_append)
                d["tags"] = tags_arr

            # Save updates
            await conn.execute(
                """
                UPDATE global_simulation_cells
                SET active_chaos_tag = $1, flora_biomass_data = $2, civilization_profile = $3
                WHERE cell_id = $4;
                """,
                new_active_tag,
                flora_data,
                civ_profile,
                payload.cell_id
            )
            logger.info(f"Mass Destruction Promoted to cell {payload.cell_id}. Flora zeroed. Tagged {tag_to_append}.")
            
            return {
                "status": "success",
                "cell_id": payload.cell_id,
                "message": f"Mass destruction promoted. Flora zeroed. Tagged {tag_to_append}."
            }
        
        return {"status": "success", "cell_id": payload.cell_id, "message": "No actions performed."}

@app.post("/api/quest/assemble")
async def assemble_quest(payload: QuestAssemblePayload, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Procedurally assembles a modular quest, applying dynamic mutations and story twists
    based on player history saga.
    """
    try:
        from narrative_quest_engine import DynamicNarrativeEngine
        engine = DynamicNarrativeEngine()
        async with pool.acquire() as conn:
            quest = await engine.generate_organic_story_seed(conn, payload.character_id, payload.cell_id)
            return quest
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error during quest assembly: {e}")
        raise HTTPException(status_code=500, detail=f"Quest assembly failed: {e}")

@app.post("/api/player/get-or-create")
async def get_or_create_character(pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Fetches the first character from the database or inserts a default one if none exist.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 
                character_id, character_name, health, stamina, composure, focus, trauma,
                personal_chaos_exposure, mutations
            FROM player_characters LIMIT 1;
            """
        )
        if row:
            muts = row["mutations"]
            if isinstance(muts, str):
                muts = json.loads(muts)
            elif muts is None:
                muts = []
            return {
                "character_id": str(row["character_id"]),
                "character_name": row["character_name"],
                "health": row["health"],
                "stamina": row["stamina"],
                "composure": row["composure"],
                "focus": row["focus"],
                "trauma": row["trauma"],
                "personal_chaos_exposure": float(row["personal_chaos_exposure"]),
                "mutations": muts
            }
        
        # Seed default character on the 2-8 scale
        char_id = await conn.fetchval(
            """
            INSERT INTO player_characters (
                character_name, might, endurance, finesse, reflex, vitality, fortitude,
                knowledge, logic, awareness, intuition, charm, willpower,
                health, stamina, composure, focus, trauma, personal_chaos_exposure, mutations
            )
            VALUES (
                'Hero of Legend', 4.00, 5.00, 4.00, 4.00, 5.00, 5.00,
                3.00, 4.00, 3.00, 4.00, 3.00, 4.00,
                15, 12, 11, 10, 0, 0.00, '[]'::jsonb
            )
            RETURNING character_id;
            """
        )
        
        row = await conn.fetchrow(
            """
            SELECT 
                character_id, character_name, health, stamina, composure, focus, trauma,
                personal_chaos_exposure, mutations
            FROM player_characters WHERE character_id = $1;
            """,
            char_id
        )
        muts = row["mutations"]
        if isinstance(muts, str):
            muts = json.loads(muts)
        elif muts is None:
            muts = []
        return {
            "character_id": str(row["character_id"]),
            "character_name": row["character_name"],
            "health": row["health"],
            "stamina": row["stamina"],
            "composure": row["composure"],
            "focus": row["focus"],
            "trauma": row["trauma"],
            "personal_chaos_exposure": float(row["personal_chaos_exposure"]),
            "mutations": muts
        }

@app.get("/api/player/character/{character_id}")
async def get_player_character(character_id: UUID, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Retrieves the full states, attributes, derived sub-stats and pools for a specific character by ID.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 
                character_id, character_name, health, stamina, composure, focus, trauma,
                might, endurance, finesse, reflex, vitality, fortitude,
                knowledge, logic, awareness, intuition, charm, willpower,
                personal_chaos_exposure, mutations
            FROM player_characters WHERE character_id = $1;
            """,
            character_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Character not found.")
        
        char_data = dict(row)
        
        # Parse mutations
        mutations = char_data["mutations"]
        if isinstance(mutations, str):
            mutations = json.loads(mutations)
        elif mutations is None:
            mutations = []
            
        # Calculate derived capacities and sub-stats
        from rpg_stat_core import (
            calculate_max_health, calculate_max_stamina, calculate_max_composure, calculate_max_focus,
            get_derived_substats
        )
        
        char_stats = {
            "might": float(char_data["might"]),
            "endurance": float(char_data["endurance"]),
            "finesse": float(char_data["finesse"]),
            "reflex": float(char_data["reflex"]),
            "vitality": float(char_data["vitality"]),
            "fortitude": float(char_data["fortitude"]),
            "knowledge": float(char_data["knowledge"]),
            "logic": float(char_data["logic"]),
            "awareness": float(char_data["awareness"]),
            "intuition": float(char_data["intuition"]),
            "charm": float(char_data["charm"]),
            "willpower": float(char_data["willpower"]),
        }
        
        max_h = calculate_max_health(char_stats["endurance"], char_stats["fortitude"], char_stats["vitality"])
        max_s = calculate_max_stamina(char_stats["might"], char_stats["reflex"], char_stats["finesse"])
        max_c = calculate_max_composure(char_stats["willpower"], char_stats["logic"], char_stats["charm"])
        max_f = calculate_max_focus(char_stats["knowledge"], char_stats["awareness"], char_stats["intuition"])
        
        substats = get_derived_substats(char_stats)
        
        return {
            "character_id": str(char_data["character_id"]),
            "character_name": char_data["character_name"],
            "health": char_data["health"],
            "stamina": char_data["stamina"],
            "composure": char_data["composure"],
            "focus": char_data["focus"],
            "trauma": char_data["trauma"],
            "personal_chaos_exposure": float(char_data["personal_chaos_exposure"]),
            "mutations": mutations,
            "stats": char_stats,
            "derived_substats": substats,
            "max_capacities": {
                "max_health": max_h,
                "max_stamina": max_s,
                "max_composure": max_c,
                "max_focus": max_f
            }
        }

@app.post("/api/player/update-pools")
async def update_player_pools(payload: PlayerPoolsUpdatePayload, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Executes a secure UPDATE on the player_characters table using a parameterized query
    to update the active resource pools (health, stamina, composure, focus), trauma,
    personal_chaos_exposure, and mutations. Automatically enforces maximum capacity caps
    based on character attributes and check for mutation triggers if chaos exposure spikes.
    """
    async with pool.acquire() as conn:
        # Fetch the character stats and current mutations/exposure
        char_row = await conn.fetchrow(
            """
            SELECT 
                might, endurance, finesse, reflex, vitality, fortitude,
                knowledge, logic, awareness, intuition, charm, willpower,
                personal_chaos_exposure, mutations
            FROM player_characters WHERE character_id = $1;
            """,
            payload.character_id
        )
        if not char_row:
            raise HTTPException(status_code=404, detail=f"Player character with ID {payload.character_id} not found.")
            
        from rpg_stat_core import (
            calculate_max_health, calculate_max_stamina, calculate_max_composure, calculate_max_focus,
            check_mutation
        )
        
        max_h = calculate_max_health(char_row["endurance"], char_row["fortitude"], char_row["vitality"])
        max_s = calculate_max_stamina(char_row["might"], char_row["reflex"], char_row["finesse"])
        max_c = calculate_max_composure(char_row["willpower"], char_row["logic"], char_row["charm"])
        max_f = calculate_max_focus(char_row["knowledge"], char_row["awareness"], char_row["intuition"])
        
        # Cap current pools
        health = min(max_h, payload.health)
        stamina = min(max_s, payload.stamina)
        composure = min(max_c, payload.composure)
        focus = min(max_f, payload.focus)
        
        # Determine updated chaos exposure and mutations
        curr_exposure = float(char_row["personal_chaos_exposure"])
        curr_mutations = char_row["mutations"]
        if isinstance(curr_mutations, str):
            curr_mutations = json.loads(curr_mutations)
        elif curr_mutations is None:
            curr_mutations = []
            
        new_exposure = payload.personal_chaos_exposure if payload.personal_chaos_exposure is not None else curr_exposure
        new_mutations = list(payload.mutations) if payload.mutations is not None else list(curr_mutations)
        
        # Trigger Mutation Factor check
        threshold = getattr(app.state, "config", {}).get("mutation_threshold", 90.0)
        new_mutation = check_mutation(new_exposure, new_mutations, threshold=threshold)
        if new_mutation:
            new_mutations.append(new_mutation)
            logger.info(f"MUTATION TRIGGERED: Character {payload.character_id} gained mutation: {new_mutation}")
            
        # Update database
        row = await conn.fetchrow(
            """
            UPDATE player_characters
            SET 
                health = $1,
                stamina = $2,
                composure = $3,
                focus = $4,
                trauma = $5,
                personal_chaos_exposure = $6,
                mutations = $7
            WHERE character_id = $8
            RETURNING character_id, character_name, personal_chaos_exposure, mutations;
            """,
            health,
            stamina,
            composure,
            focus,
            payload.trauma,
            new_exposure,
            new_mutations,
            payload.character_id
        )
        
        updated_muts = row["mutations"]
        if isinstance(updated_muts, str):
            updated_muts = json.loads(updated_muts)
        elif updated_muts is None:
            updated_muts = []
            
        return {
            "status": "success",
            "character_id": str(row["character_id"]),
            "character_name": row["character_name"],
            "health": health,
            "stamina": stamina,
            "composure": composure,
            "focus": focus,
            "personal_chaos_exposure": float(row["personal_chaos_exposure"]),
            "mutations": updated_muts,
            "new_mutation_triggered": new_mutation
        }

@app.post("/api/combat/resolve-clash")
async def resolve_combat_clash(payload: ClashResolvePayload, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Resolves a contested clash between the player and an opponent.
    If rolls tie, deducts 1 Stamina and 1 Focus token from the player (persisted in DB).
    """
    async with pool.acquire() as conn:
        # Fetch character stats to calculate Perception
        char_row = await conn.fetchrow(
            """
            SELECT 
                health, stamina, composure, focus, trauma,
                might, endurance, finesse, reflex, vitality, fortitude,
                knowledge, logic, awareness, intuition, charm, willpower,
                personal_chaos_exposure, mutations
            FROM player_characters WHERE character_id = $1;
            """,
            payload.character_id
        )
        if not char_row:
            raise HTTPException(status_code=404, detail="Character not found.")
            
        from rpg_stat_core import resolve_contested_clash, get_derived_substats
        
        char_stats = {
            "might": float(char_row["might"]),
            "endurance": float(char_row["endurance"]),
            "finesse": float(char_row["finesse"]),
            "reflex": float(char_row["reflex"]),
            "vitality": float(char_row["vitality"]),
            "fortitude": float(char_row["fortitude"]),
            "knowledge": float(char_row["knowledge"]),
            "logic": float(char_row["logic"]),
            "awareness": float(char_row["awareness"]),
            "intuition": float(char_row["intuition"]),
            "charm": float(char_row["charm"]),
            "willpower": float(char_row["willpower"]),
        }
        derived = get_derived_substats(char_stats)
        player_perception = derived["perception"]
        
        clash_result = resolve_contested_clash(
            player_perception, payload.opponent_perception,
            payload.tactic_a, payload.tactic_b,
            payload.roll_a, payload.roll_b
        )
        
        # If tie, deduct tokens from player
        if clash_result["is_tie"]:
            new_stamina = max(0, char_row["stamina"] - clash_result["stamina_deduction"])
            new_focus = max(0, char_row["focus"] - clash_result["focus_deduction"])
            
            await conn.execute(
                """
                UPDATE player_characters
                SET stamina = $1, focus = $2
                WHERE character_id = $3;
                """,
                new_stamina, new_focus, payload.character_id
            )
            clash_result["player_updated_stamina"] = new_stamina
            clash_result["player_updated_focus"] = new_focus
        else:
            clash_result["player_updated_stamina"] = char_row["stamina"]
            clash_result["player_updated_focus"] = char_row["focus"]
            
        return clash_result

@app.post("/api/chaos/burn")
async def execute_chaos_burn(payload: ChaosBurnPayload, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Triggers a Reserve Burn: Channels the Chaos when trying to act with 0 resource tokens.
    Rolls 1d100 against personal_chaos_exposure, potentially triggering double effect or Wild Resonance,
    and handles permanent mutations if exposure exceeds 90.
    """
    async with pool.acquire() as conn:
        char_row = await conn.fetchrow(
            """
            SELECT personal_chaos_exposure, mutations FROM player_characters WHERE character_id = $1;
            """,
            payload.character_id
        )
        if not char_row:
            raise HTTPException(status_code=404, detail="Character not found.")
            
        from rpg_stat_core import channel_the_chaos, check_mutation
        
        curr_exposure = float(char_row["personal_chaos_exposure"])
        curr_mutations = char_row["mutations"]
        if isinstance(curr_mutations, str):
            curr_mutations = json.loads(curr_mutations)
        elif curr_mutations is None:
            curr_mutations = []
            
        burn_result = channel_the_chaos(curr_exposure, payload.d100_roll)
        new_exposure = burn_result["new_exposure"]
        new_mutations = list(curr_mutations)
        
        # Check for mutation
        threshold = getattr(app.state, "config", {}).get("mutation_threshold", 90.0)
        new_mutation = check_mutation(new_exposure, new_mutations, threshold=threshold)
        if new_mutation:
            new_mutations.append(new_mutation)
            burn_result["new_mutation_triggered"] = new_mutation
        else:
            burn_result["new_mutation_triggered"] = None
            
        # Save updated exposure and mutations to DB
        await conn.execute(
            """
            UPDATE player_characters
            SET personal_chaos_exposure = $1, mutations = $2
            WHERE character_id = $3;
            """,
            new_exposure, new_mutations, payload.character_id
        )
        
        burn_result["final_exposure"] = new_exposure
        burn_result["final_mutations"] = new_mutations
        
        return burn_result

@app.get("/api/world-map/crust-mesh")
async def get_crust_mesh(pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Returns the raw geographic data for all 90,000 cells of the world map.
    Optimized for high-speed retrieval and direct Kivy client rendering.
    Enriched with cult_index to support web dashboard visualizations.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                cell_id, 
                coord_x, 
                coord_y, 
                elevation_meters::float AS elevation_meters, 
                temperature_celsius::float AS temperature_celsius, 
                moisture_index::float AS moisture_index,
                (COALESCE(shadow_war_metrics->>'cult_infiltration_index', shadow_war_metrics->>'subversion', '0.0'))::float AS cult_index
            FROM global_simulation_cells
            ORDER BY cell_id;
            """
        )
        return [dict(row) for row in rows]

@app.get("/api/cell/{cell_id}/chaos-context")
async def get_cell_chaos_context(cell_id: int, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Runs a LEFT JOIN between global_simulation_cells and sovereign_cosmic_powers
    to return the active_tag, aligned_character_stat, target_resource_pool, and
    base_fallout_profile for the specific cell ID.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 
                g.cell_id,
                g.active_chaos_tag AS active_tag,
                p.aligned_character_stat,
                p.target_resource_pool,
                p.base_fallout_profile
            FROM global_simulation_cells g
            LEFT JOIN sovereign_cosmic_powers p 
              ON (g.active_chaos_tag = p.name OR g.active_chaos_tag = '#Epicenter_' || p.name)
            WHERE g.cell_id = $1;
            """,
            cell_id
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Simulation cell {cell_id} not found.")
        return dict(row)

@app.get("/api/cell/{cell_id}/ecology")
async def get_cell_ecology(cell_id: int, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Returns the cell's parsed flora_biomass_data, parsed fauna_population_data,
    and the active_chaos_tag to serve the player viewport.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 
                flora_biomass_data, 
                fauna_population_data, 
                active_chaos_tag
            FROM global_simulation_cells 
            WHERE cell_id = $1;
            """,
            cell_id
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Simulation cell {cell_id} not found.")
        return {
            "cell_id": cell_id,
            "flora_biomass_data": row["flora_biomass_data"],
            "fauna_population_data": row["fauna_population_data"],
            "active_chaos_tag": row["active_chaos_tag"]
        }

@app.get("/api/world-map/geopolitical-mesh")
async def get_geopolitical_mesh(pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Returns the geopolitical data for all aligned faction cells of the world map.
    Includes cell_id, coord_x, coord_y, faction_alignment, and tier.
    Optimized for high-speed retrieval and direct Kivy client border rendering.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                cell_id, 
                coord_x, 
                coord_y, 
                COALESCE(civilization_profile->>'faction', civilization_profile->>'controlling_faction_id') AS faction_alignment, 
                civilization_profile->>'tier' AS tier 
            FROM global_simulation_cells
            WHERE (civilization_profile->>'faction' IS NOT NULL AND civilization_profile->>'faction' != '#Independent')
               OR (civilization_profile->>'controlling_faction_id' IS NOT NULL AND civilization_profile->>'controlling_faction_id' != '#Independent')
            ORDER BY cell_id;
            """
        )
        return [dict(row) for row in rows]

@app.get("/api/cell/{cell_id}/shadow-intel")
async def get_shadow_intel(cell_id: int, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Returns the cell's shadow war intelligence metrics:
    - cell_id
    - exact_cult_index (subversion / cult_infiltration_index)
    - exact_warden_index (infiltration / warden_presence)
    - active_chaos_tag
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 
                cell_id, 
                shadow_war_metrics, 
                active_chaos_tag 
            FROM global_simulation_cells 
            WHERE cell_id = $1;
            """,
            cell_id
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Simulation cell {cell_id} not found.")
        
        metrics = row["shadow_war_metrics"]
        if isinstance(metrics, str):
            metrics_data = json.loads(metrics)
        else:
            metrics_data = metrics or {}
            
        exact_cult_index = metrics_data.get("cult_infiltration_index", metrics_data.get("subversion", 0.0))
        exact_warden_index = metrics_data.get("warden_presence", metrics_data.get("infiltration", 0.0))
        
        return {
            "cell_id": row["cell_id"],
            "exact_cult_index": exact_cult_index,
            "exact_warden_index": exact_warden_index,
            "active_chaos_tag": row["active_chaos_tag"]
        }

@app.post("/api/saga/record-event")
async def record_saga_event(payload: SagaEventPayload, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Records a gameplay choice event into player_saga_stack queue.
    Enriches the event payload with regional metrics from global_simulation_cells
    and temporal coordinates from system_clock.
    """
    async with pool.acquire() as conn:
        # 1. Fetch cell details for enrichment
        cell_row = await conn.fetchrow(
            """
            SELECT 
                coord_x,
                coord_y,
                active_chaos_tag,
                shadow_war_metrics,
                elevation_meters::float AS elevation,
                temperature_celsius::float AS temperature,
                moisture_index::float AS moisture,
                COALESCE(civilization_profile->>'faction', civilization_profile->>'controlling_faction_id') AS faction,
                civilization_profile->>'tier' AS tier
            FROM global_simulation_cells
            WHERE cell_id = $1;
            """,
            payload.target_cell_id
        )
        if not cell_row:
            raise HTTPException(status_code=404, detail=f"Simulation cell {payload.target_cell_id} not found.")

        # 2. Fetch current system clock
        clock_row = await conn.fetchrow(
            "SELECT current_year, current_day, current_segment FROM system_clock WHERE id = 1;"
        )
        clock_data = dict(clock_row) if clock_row else {"current_year": 1, "current_day": 1, "current_segment": 0}

        # 3. Parse cell metrics and handle shadow war JSON conversion
        metrics = dict(cell_row)
        shadow_metrics = metrics.get("shadow_war_metrics") or {}
        if isinstance(shadow_metrics, str):
            try:
                shadow_metrics = json.loads(shadow_metrics)
            except:
                shadow_metrics = {}

        cult_infiltration = shadow_metrics.get("cult_infiltration_index", shadow_metrics.get("subversion", 0.0))
        warden_presence = shadow_metrics.get("warden_presence", shadow_metrics.get("infiltration", 0.0))

        # 4. Construct context payload with ambient regional metrics
        context_payload = {
            "gameplay_choices": payload.gameplay_choices or {},
            "system_clock": clock_data,
            "ambient_metrics": {
                "active_chaos_tag": metrics.get("active_chaos_tag") or "StableReality",
                "cult_infiltration_index": float(cult_infiltration),
                "warden_presence": float(warden_presence),
                "elevation_meters": metrics.get("elevation"),
                "temperature_celsius": metrics.get("temperature"),
                "moisture_index": metrics.get("moisture"),
                "faction": metrics.get("faction") or "#Independent",
                "tier": metrics.get("tier") or "Wilderness",
                "coord_x": metrics.get("coord_x"),
                "coord_y": metrics.get("coord_y")
            }
        }

        # 5. Insert record into player_saga_stack table
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO player_saga_stack (
                    character_id,
                    target_cell_id,
                    event_type,
                    stat_used,
                    roll_result,
                    context_payload
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING event_id;
                """,
                payload.character_id,
                payload.target_cell_id,
                payload.event_type,
                payload.stat_used,
                payload.roll_result,
                context_payload
            )
            if not row:
                raise HTTPException(status_code=500, detail="Failed to record saga event.")
            return {"status": "success", "event_id": str(row["event_id"])}
        except asyncpg.exceptions.ForeignKeyViolationError as e:
            # Most likely character_id does not exist
            raise HTTPException(
                status_code=400,
                detail=f"Foreign key violation: Ensure the character_id '{payload.character_id}' exists in player_characters."
            )

# ============================================================================
# PLANETARY BUILDER ADMIN ENDPOINTS
# ============================================================================

@app.get("/api/builder/crust-mesh")
async def get_builder_crust_mesh(pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Returns the complete climate AND active chaos tag data for all 90,000 cells.
    Used by the Admin PlanetaryBuilderDashboard to render the entire grid and biomes accurately.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                coord_x, 
                coord_y, 
                elevation_meters::float AS elevation_meters, 
                temperature_celsius::float AS temperature_celsius, 
                moisture_index::float AS moisture_index,
                active_chaos_tag
            FROM global_simulation_cells
            ORDER BY cell_id;
            """
        )
        return [dict(row) for row in rows]

@app.post("/api/builder/generate-crust")
async def generate_crust_endpoint():
    """
    Fires a POST request to trigger the crust_seeder.py logic.
    Utilizes OpenSimplex noise to overwrite the 90,000 PostgreSQL cells with base land, ocean, and elevation values.
    """
    try:
        from crust_seeder import seed_crust
        await seed_crust()
        return {"status": "success", "message": "Base crust generated and 90,000 cells overwritten successfully."}
    except Exception as e:
        logger.error(f"Error during crust seeding: {e}")
        raise HTTPException(status_code=500, detail=f"Crust seeding failed: {str(e)}")

@app.post("/api/builder/paint")
async def paint_endpoint(payload: BrushStrokePlacement, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Paint brush stroke batch update. Updates regional climate coordinates or chaos tags in bulk.
    """
    if not payload.cells:
        return {"status": "success", "message": "No cells to paint."}
        
    async with pool.acquire() as conn:
        async with conn.transaction():
            # If climate override: elevation, temperature, moisture are provided.
            # We must update coordinates, but we also must update flora, fauna, civ, shadow by calling get_biome_payloads.
            if payload.elevation is not None and payload.temperature is not None and payload.moisture is not None:
                from crust_seeder import get_biome_payloads
                flora, fauna, civ, shadow = get_biome_payloads(payload.elevation, payload.temperature, payload.moisture)
                
                active_chaos_tag = None
                if payload.elevation > 3000.0:
                    active_chaos_tag = "Cosmic Winds"
                elif payload.temperature < -15.0:
                    active_chaos_tag = "Eternal Frost"
                
                update_query = """
                    UPDATE global_simulation_cells
                    SET 
                        elevation_meters = $1,
                        temperature_celsius = $2,
                        moisture_index = $3,
                        flora_biomass_data = $4,
                        fauna_population_data = $5,
                        civilization_profile = $6,
                        shadow_war_metrics = $7,
                        active_chaos_tag = COALESCE($8, active_chaos_tag)
                    WHERE coord_x = $9 AND coord_y = $10;
                """
                # Prepare data list
                data_list = []
                for cell in payload.cells:
                    data_list.append((
                        payload.elevation,
                        payload.temperature,
                        payload.moisture,
                        json.dumps(flora),
                        json.dumps(fauna),
                        json.dumps(civ),
                        json.dumps(shadow),
                        active_chaos_tag,
                        cell.x,
                        cell.y
                    ))
                await conn.executemany(update_query, data_list)
            
            # If chaos tag override:
            if payload.chaos_tag is not None:
                # If chaos_tag is "None", we set active_chaos_tag to NULL
                tag_val = None if payload.chaos_tag == "None" else payload.chaos_tag
                update_query = """
                    UPDATE global_simulation_cells
                    SET active_chaos_tag = $1
                    WHERE coord_x = $2 AND coord_y = $3;
                """
                data_list = [(tag_val, cell.x, cell.y) for cell in payload.cells]
                await conn.executemany(update_query, data_list)
                
        return {"status": "success", "message": f"Painted {len(payload.cells)} cells successfully."}

@app.websocket("/api/builder/ws")
async def builder_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time config hot-reloading without forcing a restart.
    Accepts APPLY_TEMPLATE payload.
    """
    await websocket.accept()
    logger.info("Builder WebSocket connection established.")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                action = payload.get("action")
                if action == "APPLY_TEMPLATE":
                    config_update = payload.get("config", {})
                    # Hot-reload in memory
                    for key, val in config_update.items():
                        app.state.config[key] = val
                    # Write to config.json
                    try:
                        with open("config.json", "w") as f:
                            json.dump(app.state.config, f, indent=2)
                        logger.info(f"Hot-reloaded configuration and saved to config.json: {app.state.config}")
                        await websocket.send_json({
                            "status": "success", 
                            "message": "Parameters hot-reloaded successfully.", 
                            "config": app.state.config
                        })
                    except Exception as err:
                        logger.error(f"Failed to write config.json: {err}")
                        await websocket.send_json({"status": "error", "message": f"Failed to save to config.json: {err}"})
                else:
                    await websocket.send_json({"status": "error", "message": f"Unknown action: {action}"})
            except json.JSONDecodeError:
                await websocket.send_json({"status": "error", "message": "Invalid JSON format."})
    except WebSocketDisconnect:
        logger.info("Builder WebSocket disconnected.")

# ============================================================================
# WORLD SIMULATION REGISTRIES ENDPOINTS
# ============================================================================

@app.get("/api/registry/flora")
async def get_registry_flora(pool: asyncpg.Pool = Depends(get_db_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                scientific_name, 
                common_name, 
                temp_preference_min::float AS temp_preference_min, 
                temp_preference_max::float AS temp_preference_max, 
                moisture_preference_min::float AS moisture_preference_min, 
                moisture_preference_max::float AS moisture_preference_max, 
                growth_rate_modifier::float AS growth_rate_modifier,
                harvest_resource,
                is_fatal_harvest,
                tags
            FROM registry_flora
            ORDER BY scientific_name;
            """
        )
        return [dict(row) for row in rows]

@app.post("/api/registry/flora")
async def update_registry_flora(payload: List[FloraItemPayload], pool: asyncpg.Pool = Depends(get_db_pool)):
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing_rows = await conn.fetch(
                "SELECT scientific_name, lore_embedding FROM registry_flora WHERE lore_embedding IS NOT NULL"
            )
            embeddings = {row["scientific_name"]: row["lore_embedding"] for row in existing_rows}
            
            await conn.execute("DELETE FROM registry_flora")
            
            for item in payload:
                emb = embeddings.get(item.scientific_name)
                await conn.execute(
                    """
                    INSERT INTO registry_flora (
                        scientific_name, common_name, 
                        temp_preference_min, temp_preference_max, 
                        moisture_preference_min, moisture_preference_max, 
                        growth_rate_modifier, harvest_resource,
                        is_fatal_harvest, tags, lore_embedding
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    item.scientific_name, item.common_name,
                    item.temp_preference_min, item.temp_preference_max,
                    item.moisture_preference_min, item.moisture_preference_max,
                    item.growth_rate_modifier, item.harvest_resource,
                    item.is_fatal_harvest, item.tags, emb
                )
    return {"status": "success", "message": "Flora registry updated successfully."}

@app.get("/api/registry/fauna")
async def get_registry_fauna(pool: asyncpg.Pool = Depends(get_db_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                scientific_name, 
                common_name, 
                dietary_classification, 
                base_pack_size, 
                reproduction_rate::float AS reproduction_rate,
                harvest_resource,
                is_fatal_harvest,
                tags
            FROM registry_fauna
            ORDER BY scientific_name;
            """
        )
        return [dict(row) for row in rows]

@app.post("/api/registry/fauna")
async def update_registry_fauna(payload: List[FaunaItemPayload], pool: asyncpg.Pool = Depends(get_db_pool)):
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing_rows = await conn.fetch(
                "SELECT scientific_name, lore_embedding FROM registry_fauna WHERE lore_embedding IS NOT NULL"
            )
            embeddings = {row["scientific_name"]: row["lore_embedding"] for row in existing_rows}
            
            await conn.execute("DELETE FROM registry_fauna")
            
            for item in payload:
                emb = embeddings.get(item.scientific_name)
                await conn.execute(
                    """
                    INSERT INTO registry_fauna (
                        scientific_name, common_name, 
                        dietary_classification, base_pack_size, 
                        reproduction_rate, harvest_resource,
                        is_fatal_harvest, tags, lore_embedding
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    item.scientific_name, item.common_name,
                    item.dietary_classification, item.base_pack_size,
                    item.reproduction_rate, item.harvest_resource,
                    item.is_fatal_harvest, item.tags, emb
                )
    return {"status": "success", "message": "Fauna registry updated successfully."}

@app.get("/api/registry/factions")
async def get_registry_factions(pool: asyncpg.Pool = Depends(get_db_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                faction_name, 
                ideology_type, 
                reputation_baseline::int AS reputation_baseline,
                faction_type,
                expansion_level::int AS expansion_level,
                aggression_level::int AS aggression_level,
                trade_level::int AS trade_level,
                government_type,
                tags,
                faction_trait
            FROM registry_factions
            ORDER BY faction_name;
            """
        )
        return [dict(row) for row in rows]

@app.post("/api/registry/factions")
async def update_registry_factions(payload: List[FactionItemPayload], pool: asyncpg.Pool = Depends(get_db_pool)):
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing_rows = await conn.fetch(
                "SELECT faction_name, lore_embedding FROM registry_factions WHERE lore_embedding IS NOT NULL"
            )
            embeddings = {row["faction_name"]: row["lore_embedding"] for row in existing_rows}
            
            await conn.execute("DELETE FROM registry_factions")
            
            for item in payload:
                emb = embeddings.get(item.faction_name)
                await conn.execute(
                    """
                    INSERT INTO registry_factions (
                        faction_name, ideology_type, 
                        reputation_baseline, faction_type,
                        expansion_level, aggression_level,
                        trade_level, government_type,
                        tags, faction_trait, lore_embedding
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    item.faction_name, item.ideology_type,
                    item.reputation_baseline, item.faction_type,
                    item.expansion_level, item.aggression_level,
                    item.trade_level, item.government_type,
                    item.tags, item.faction_trait, emb
                )
    return {"status": "success", "message": "Faction registry updated successfully."}

@app.get("/api/registry/races")
async def get_registry_races(pool: asyncpg.Pool = Depends(get_db_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                race_name, 
                genus_type, 
                associated_faction_name,
                temp_preference_min::float AS temp_preference_min, 
                temp_preference_max::float AS temp_preference_max, 
                moisture_preference_min::float AS moisture_preference_min, 
                moisture_preference_max::float AS moisture_preference_max, 
                reproduction_rate::float AS reproduction_rate,
                food_consumption_rate::float AS food_consumption_rate
            FROM registry_races
            ORDER BY race_name;
            """
        )
        return [dict(row) for row in rows]

@app.post("/api/registry/races")
async def update_registry_races(payload: List[RaceItemPayload], pool: asyncpg.Pool = Depends(get_db_pool)):
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing_rows = await conn.fetch(
                "SELECT race_name, lore_embedding FROM registry_races WHERE lore_embedding IS NOT NULL"
            )
            embeddings = {row["race_name"]: row["lore_embedding"] for row in existing_rows}
            
            await conn.execute("DELETE FROM registry_races")
            
            for item in payload:
                emb = embeddings.get(item.race_name)
                await conn.execute(
                    """
                    INSERT INTO registry_races (
                        race_name, genus_type, associated_faction_name,
                        temp_preference_min, temp_preference_max, 
                        moisture_preference_min, moisture_preference_max, 
                        reproduction_rate, food_consumption_rate, lore_embedding
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    item.race_name, item.genus_type, item.associated_faction_name,
                    item.temp_preference_min, item.temp_preference_max,
                    item.moisture_preference_min, item.moisture_preference_max,
                    item.reproduction_rate, item.food_consumption_rate, emb
                )
    return {"status": "success", "message": "Races registry updated successfully."}

# ============================================================================
# WEB DASHBOARD SERVING ENDPOINTS
# ============================================================================

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    """
    Serves the read-only Web Dashboard HTML interface.
    """
    try:
        with open(os.path.join("static", "dashboard.html"), "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dashboard file static/dashboard.html not found.")

# Mount static file serving directory
app.mount("/static", StaticFiles(directory="static"), name="static")

class HandshakePayload(BaseModel):
    region_x: int
    region_y: int

@app.post("/api/world/handshake")
async def process_world_handshake(payload: HandshakePayload, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Called strictly on a border-cross event. Pulls pre-calculated macro variables
    from the database for a single Region cell.
    """
    async with pool.acquire() as conn:
        # A Region is represented in the DB as a coordinate on the global_simulation_cells (which maps 300x300 continent cells)
        # Assuming payload.region_x and region_y are actually mapping to the global coord_x, coord_y for that specific tier
        # For this simulation engine, let's query the specific cell matching the parameters.
        # Often the client asks for specific px/py on the 300x300 grid via region vars. Let's pull those.
        # But wait, looking at the schema, the client asks for cell_id via px/py in its original codebase: `cell_id = py * 300 + px + 1`
        # Let's adjust this handshake to just fetch the macro variables for the coordinates provided.
        row = await conn.fetchrow(
            """
            SELECT
                elevation_meters, temperature_celsius, moisture_index, active_chaos_tag,
                flora_biomass_data, fauna_population_data, civilization_profile, shadow_war_metrics
            FROM global_simulation_cells
            WHERE coord_x = $1 AND coord_y = $2
            """,
            payload.region_x, payload.region_y
        )

        if not row:
            return {"status": "error", "message": "Region not found."}

        return {
            "status": "success",
            "region_x": payload.region_x,
            "region_y": payload.region_y,
            "data": dict(row)
        }

@app.post("/api/narrative/trigger-ai-director")
async def trigger_ai_director(pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Manually triggers the Paragon AI Director to stage and resolve regional crises.
    Useful for testing and manual clock advances.
    """
    if not hasattr(app.state, "ai_director") or app.state.ai_director is None:
        raise HTTPException(status_code=500, detail="AI Director is not initialized.")
    try:
        # Trigger stage_crises
        await app.state.ai_director.stage_crises()
        
        # Process whatever is in the queue immediately (synchronously for the API call)
        processed = []
        while not app.state.ai_director.queue.empty():
            event = await app.state.ai_director.queue.get()
            await app.state.ai_director.process_crisis_event(event)
            processed.append({
                "cell_id": event["cell_id"],
                "paragon_name": event["paragon"]["name"],
                "intent": event["paragon"].get("mechanical_intent", "Unknown")
            })
        return {"status": "success", "processed_events": processed}
    except Exception as e:
        logger.error(f"Manual AI Director execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Manual execution failed: {e}")

@app.post("/api/narrative/ingest-vault")
async def ingest_vault(pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Triggers the ingestion hook to parse, chunk, and embed Chronicles from the Obsidian vault.
    """
    vault_path = app.state.config.get("ai_director_config", {}).get("obsidian_vault_path", "C:/Users/krazy/Documents/Shatterlands")
    try:
        from lore_pipeline import ingest_obsidian_vault
        num_files, num_chunks = await ingest_obsidian_vault(pool, vault_path)
        return {
            "status": "success",
            "message": f"Successfully loaded {num_files} files generating {num_chunks} lore records."
        }
    except Exception as e:
        logger.error(f"Vault ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

@app.post("/api/narrative/search-lore")
async def search_lore(payload: SearchLorePayload, pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Performs a hybrid search (relational filter + vector distance) over the campaign lore ledger.
    """
    try:
        from narrative_quest_engine import generate_text_embedding
        from lore_pipeline import query_hybrid_campaign_lore
        
        query_vector = generate_text_embedding(payload.query, 1536)
        
        async with pool.acquire() as conn:
            rows = await query_hybrid_campaign_lore(
                conn, query_vector, payload.faction_tag, payload.associated_cell_id
            )
            
            results = []
            for r in rows:
                results.append({
                    "ledger_id": r["ledger_id"],
                    "associated_cell_id": r["associated_cell_id"],
                    "faction_tag": r["faction_tag"],
                    "raw_history_summary": r["raw_history_summary"],
                    "similarity": float(1.0 - r["cosine_dist"]) if r.get("cosine_dist") is not None else 0.0,
                    "recorded_at": r["recorded_at"].isoformat() if r["recorded_at"] else None
                })
            return {"status": "success", "results": results}
    except Exception as e:
        logger.error(f"Lore search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
