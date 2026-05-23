-- ============================================================================
-- Planetary-Scale Simulation Engine - Database Schema Initialization
-- ============================================================================

-- Enable the pgvector extension to support high-dimensional embeddings
-- for hybrid narrative, story state, and lore retrieval systems.
-- (pgvector extension commented out for compatibility with environment)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- 1. SYSTEM CLOCK
-- ============================================================================
-- Tracks the current temporal coordinates of the simulation engine.
-- Enforces a strict single-row pattern to ensure clock synchronization.
CREATE TABLE system_clock (
    id INTEGER PRIMARY KEY DEFAULT 1,
    current_year INTEGER NOT NULL DEFAULT 1,
    current_day INTEGER NOT NULL DEFAULT 1,
    current_segment INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT chk_system_clock_single_row CHECK (id = 1),
    CONSTRAINT chk_current_segment_bounds CHECK (current_segment >= 0 AND current_segment <= 23)
);

COMMENT ON TABLE system_clock IS 'Tracks current simulation time with single-row constraint enforcement.';
COMMENT ON COLUMN system_clock.current_segment IS 'Tracks the hour/segment of the current day (0 to 23).';

-- Insert the baseline starting row
INSERT INTO system_clock (id, current_year, current_day, current_segment)
VALUES (1, 1, 1, 0)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- 2. COSMIC & CALENDAR LEDGERS
-- ============================================================================
-- Sovereign Cosmic Powers representing foundational planar forces.
CREATE TABLE sovereign_cosmic_powers (
    power_id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    influence_domain VARCHAR(100) NOT NULL,
    base_resonance NUMERIC(5, 2) NOT NULL DEFAULT 1.00,
    lore_embedding REAL[],
    aligned_character_stat VARCHAR(100),
    target_resource_pool VARCHAR(100),
    base_fallout_profile JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE sovereign_cosmic_powers IS 'Tracks high-level cosmic forces, their domains, and influence scales.';
COMMENT ON COLUMN sovereign_cosmic_powers.lore_embedding IS 'Vector embedding of lore/descriptions for semantic retrieval.';
COMMENT ON COLUMN sovereign_cosmic_powers.aligned_character_stat IS 'The character attribute aligned to this power.';
COMMENT ON COLUMN sovereign_cosmic_powers.target_resource_pool IS 'The pool targeted by fallout (health, stamina, composure, focus).';
COMMENT ON COLUMN sovereign_cosmic_powers.base_fallout_profile IS 'Attributes of the cosmic fallout (damage type, base values).';

-- Spatial Sovereign Anchors tracking the 12 cosmic anchor points.
CREATE TABLE spatial_sovereign_anchors (
    anchor_id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    associated_power_id INTEGER REFERENCES sovereign_cosmic_powers(power_id) ON DELETE SET NULL,
    coord_x INTEGER NOT NULL,
    coord_y INTEGER NOT NULL,
    resonance_frequency NUMERIC(8, 3) NOT NULL DEFAULT 1.000,
    active_status BOOLEAN NOT NULL DEFAULT TRUE,
    lore_embedding REAL[]
);

COMMENT ON TABLE spatial_sovereign_anchors IS 'Tracks the 12 sovereign cosmic anchors tied to planar forces.';

-- Calendar Configuration tracking erratic moon orbital trajectory.
CREATE TABLE calendar_configuration (
    segment_id INTEGER PRIMARY KEY,
    segment_name VARCHAR(255) NOT NULL,
    moon_focal_x NUMERIC(6, 2) NOT NULL,
    moon_focal_y NUMERIC(6, 2) NOT NULL,
    CONSTRAINT chk_segment_id_bounds CHECK (segment_id >= 0 AND segment_id <= 23)
);

COMMENT ON TABLE calendar_configuration IS 'Configures erratic moon coordinates shifting dynamically over hourly ticks.';
COMMENT ON COLUMN calendar_configuration.segment_id IS 'Current active temporal segment index (0 to 23).';
COMMENT ON COLUMN calendar_configuration.segment_name IS 'Label representing the orbital segment phase.';
COMMENT ON COLUMN calendar_configuration.moon_focal_x IS 'Computed focal X-coordinate of the erratic moon.';
COMMENT ON COLUMN calendar_configuration.moon_focal_y IS 'Computed focal Y-coordinate of the erratic moon.';

-- ============================================================================
-- 3. MASTER CREATION REGISTRIES
-- ============================================================================
-- Master templates for Flora.
CREATE TABLE registry_flora (
    flora_id SERIAL PRIMARY KEY,
    scientific_name VARCHAR(255) UNIQUE NOT NULL,
    common_name VARCHAR(255) NOT NULL,
    temp_preference_min NUMERIC(5, 2) NOT NULL,
    temp_preference_max NUMERIC(5, 2) NOT NULL,
    moisture_preference_min NUMERIC(4, 3) NOT NULL,
    moisture_preference_max NUMERIC(4, 3) NOT NULL,
    growth_rate_modifier NUMERIC(4, 2) NOT NULL DEFAULT 1.00,
    lore_embedding REAL[]
);

COMMENT ON TABLE registry_flora IS 'World-building template catalog for plant life in the simulation.';

-- Master templates for Fauna.
CREATE TABLE registry_fauna (
    fauna_id SERIAL PRIMARY KEY,
    scientific_name VARCHAR(255) UNIQUE NOT NULL,
    common_name VARCHAR(255) NOT NULL,
    dietary_classification VARCHAR(100) NOT NULL,
    base_pack_size INTEGER NOT NULL DEFAULT 1,
    reproduction_rate NUMERIC(4, 2) NOT NULL DEFAULT 1.00,
    lore_embedding REAL[]
);

COMMENT ON TABLE registry_fauna IS 'World-building template catalog for animal life in the simulation.';

-- Master templates for Factions.
CREATE TABLE registry_factions (
    faction_id SERIAL PRIMARY KEY,
    faction_name VARCHAR(255) UNIQUE NOT NULL,
    ideology_type VARCHAR(100) NOT NULL,
    reputation_baseline INTEGER NOT NULL DEFAULT 0,
    lore_embedding REAL[]
);

COMMENT ON TABLE registry_factions IS 'Registry of existing factions, political units, or sovereign groups.';

-- Faction starting parameters for simulation world generation.
CREATE TABLE genesis_faction_seeds (
    seed_id SERIAL PRIMARY KEY,
    faction_name VARCHAR(255) UNIQUE NOT NULL,
    ideal_elevation_min NUMERIC(8, 2) NOT NULL,
    ideal_elevation_max NUMERIC(8, 2) NOT NULL,
    preferred_active_chaos_tag VARCHAR(100),
    starting_population INTEGER NOT NULL DEFAULT 100,
    seed_parameters JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE genesis_faction_seeds IS 'Seeds defining preferences and starting state parameters for faction placement during world gen.';

-- ============================================================================
-- 4. THE MACRO GRID
-- ============================================================================
-- Grid cells mapping the global physical simulation layout.
CREATE TABLE global_simulation_cells (
    cell_id BIGSERIAL PRIMARY KEY,
    coord_x INTEGER NOT NULL,
    coord_y INTEGER NOT NULL,
    elevation_meters NUMERIC(8, 2) NOT NULL DEFAULT 0.00,
    temperature_celsius NUMERIC(5, 2) NOT NULL DEFAULT 15.00,
    moisture_index NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
    active_chaos_tag VARCHAR(100) DEFAULT NULL,
    
    -- Native JSONB Columns with robust default baseline structures
    flora_biomass_data JSONB NOT NULL DEFAULT '{"biomass_index": 0.00, "growth_stage": "dormant", "dominant_species_id": null}'::jsonb,
    fauna_population_data JSONB NOT NULL DEFAULT '{"populations": [], "total_count": 0, "dominant_species_id": null}'::jsonb,
    civilization_profile JSONB NOT NULL DEFAULT '{"controlling_faction_id": null, "development_index": 0.00, "has_settlement": false}'::jsonb,
    shadow_war_metrics JSONB NOT NULL DEFAULT '{"unrest": 0.00, "subversion": 0.00, "corruption": 0.00, "infiltration": 0.00}'::jsonb,
    
    CONSTRAINT uq_global_cells_coords UNIQUE (coord_x, coord_y),
    CONSTRAINT chk_moisture_index_range CHECK (moisture_index >= 0.000 AND moisture_index <= 1.000)
);

COMMENT ON TABLE global_simulation_cells IS 'Macro grid cells forming the physical layout of the planetary simulation.';
COMMENT ON COLUMN global_simulation_cells.flora_biomass_data IS 'Biomass calculations, active flora species, and development stages.';
COMMENT ON COLUMN global_simulation_cells.fauna_population_data IS 'Tracked populations, migration density, and counts.';
COMMENT ON COLUMN global_simulation_cells.civilization_profile IS 'Sovereignty, local infrastructure level, and economic indices.';
COMMENT ON COLUMN global_simulation_cells.shadow_war_metrics IS 'Metrics for local subversion, corruption, unrest, and infiltration.';

-- Spatial index on coordinate fields to speed up distance, neighbor, and layout queries.
CREATE INDEX idx_global_cells_coords ON global_simulation_cells (coord_x, coord_y);

-- ============================================================================
-- 5. THE 5TH LAYER (INTERIOR CACHING)
-- ============================================================================
-- Manages cached state changes, inventories, and maps for virtual interior sub-layers.
CREATE TABLE interior_persistency_deltas (
    interior_instance_id VARCHAR(255) PRIMARY KEY,
    container_inventories JSONB NOT NULL DEFAULT '{}'::jsonb,
    dropped_floor_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    structural_changes JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE interior_persistency_deltas IS 'Caches modifications, item locations, and inventories within specific indoor or underground sub-instances.';

-- ============================================================================
-- 6. PLAYER LEDGER
-- ============================================================================
-- Tracks player characters, attributes, and resources.
CREATE TABLE player_characters (
    character_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_name VARCHAR(255) NOT NULL,
    
    -- Core Attributes (defaulting to 2.50 as a fallback default for simulation/gameplay modifications)
    might NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    endurance NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    finesse NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    reflex NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    vitality NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    fortitude NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    knowledge NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    logic NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    awareness NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    intuition NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    charm NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    willpower NUMERIC(4, 2) NOT NULL DEFAULT 2.50,
    
    -- Active Resource Pools
    health INTEGER NOT NULL DEFAULT 100,
    stamina INTEGER NOT NULL DEFAULT 100,
    composure INTEGER NOT NULL DEFAULT 100,
    focus INTEGER NOT NULL DEFAULT 100,
    trauma INTEGER NOT NULL DEFAULT 0
);

COMMENT ON TABLE player_characters IS 'Master record for player characters, tracking attributes and dynamic resources.';
COMMENT ON COLUMN player_characters.might IS 'Physical strength, power, and carrying capabilities.';
COMMENT ON COLUMN player_characters.endurance IS 'Physical robustness, stamina retention, and resistance to exhaustion.';
COMMENT ON COLUMN player_characters.finesse IS 'Dexterity, precision, and coordination.';
COMMENT ON COLUMN player_characters.reflex IS 'Agility, speed, and reaction times.';
COMMENT ON COLUMN player_characters.vitality IS 'General life force and maximum health factors.';
COMMENT ON COLUMN player_characters.fortitude IS 'Mental and physical hardiness against environmental and magic hazards.';
COMMENT ON COLUMN player_characters.knowledge IS 'Information storage, memory, and historical recall.';
COMMENT ON COLUMN player_characters.logic IS 'Deductive reasoning, analytical processing, and puzzle-solving.';
COMMENT ON COLUMN player_characters.trauma IS 'Tracks accumulated trauma and mental stress index.';
COMMENT ON COLUMN system_clock.current_year IS 'Tracks current simulation year.';
COMMENT ON COLUMN system_clock.current_day IS 'Tracks current simulation day.';

-- ============================================================================
-- SEED DATA FOR SIMULATION ENVIRONMENT
-- ============================================================================

-- Seed sovereign_cosmic_powers
INSERT INTO sovereign_cosmic_powers (name, influence_domain, base_resonance, aligned_character_stat, target_resource_pool, base_fallout_profile) VALUES
('#Mass', 'Gravity', 1.00, 'might', 'health', '{"damage_type": "GRAVITATIONAL"}'::jsonb),
('#Ordo', 'Order', 1.00, 'endurance', 'stamina', '{"damage_type": "KINETIC_STOP"}'::jsonb),
('#Motus', 'Motion', 1.00, 'finesse', 'stamina', '{"damage_type": "SONIC_VIBRATION"}'::jsonb),
('#Flux', 'Change', 1.00, 'reflex', 'health', '{"damage_type": "METAMORPHIC"}'::jsonb),
('#Vita', 'Life', 1.00, 'vitality', 'health', '{"damage_type": "BIOMASS_SURGE"}'::jsonb),
('#Nexus', 'Arcane', 1.00, 'fortitude', 'stamina', '{"damage_type": "ARCANE_PRISM"}'::jsonb),
('#Anumis', 'Mind', 1.00, 'knowledge', 'focus', '{"damage_type": "PSYCHIC_PULSE"}'::jsonb),
('#Ratio', 'Logic', 1.00, 'logic', 'composure', '{"damage_type": "LOGICAL_AXIS"}'::jsonb),
('#Lux', 'Light', 1.00, 'awareness', 'composure', '{"damage_type": "PRISM_REFRACT"}'::jsonb),
('#Omen', 'Fate', 1.00, 'intuition', 'focus', '{"damage_type": "FATE_TWIST"}'::jsonb),
('#Aura', 'Emotion', 1.00, 'charm', 'composure', '{"damage_type": "EMOTIONAL_WAVE"}'::jsonb),
('#Lex', 'Law', 1.00, 'willpower', 'focus', '{"damage_type": "DETERMINISTIC"}'::jsonb)
ON CONFLICT (name) DO NOTHING;

-- Seed spatial_sovereign_anchors
INSERT INTO spatial_sovereign_anchors (name, associated_power_id, coord_x, coord_y, resonance_frequency, active_status) VALUES
('The Gravity Spires', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Mass'), 40, 40, 1.000, TRUE),
('The Unyielding Foundation', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Ordo'), 150, 30, 1.000, TRUE),
('The Kinetic Plains', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Motus'), 260, 40, 1.000, TRUE),
('The Shifting Mistlands', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Flux'), 30, 150, 1.000, TRUE),
('The Healing Cradle', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Vita'), 150, 60, 1.000, TRUE),
('The Eternal Sanctuary', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Nexus'), 150, 150, 1.000, TRUE),
('The Silver-Leaf Archives', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Anumis'), 270, 150, 1.000, TRUE),
('The Orchards of Sacred Geometry', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Ratio'), 40, 260, 1.000, TRUE),
('The Prism Heights', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Lux'), 260, 260, 1.000, TRUE),
('The Premonition Willows', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Omen'), 90, 90, 1.000, TRUE),
('The Gilded Vales', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Aura'), 210, 90, 1.000, TRUE),
('The Echoing Steppes', (SELECT power_id FROM sovereign_cosmic_powers WHERE name = '#Lex'), 150, 210, 1.000, TRUE)
ON CONFLICT (name) DO NOTHING;

-- Seed calendar_configuration for Luna Erraticus orbital trajectory
INSERT INTO calendar_configuration (segment_id, segment_name, moon_focal_x, moon_focal_y) VALUES
(0, 'First Dawn', 150.00, 20.00),
(1, 'Shimmering Ascent', 110.50, 55.00),
(2, 'Wobbling Drift', 60.20, 130.40),
(3, 'Erratic Zenith', 10.40, 280.90),
(4, 'Nadir Collapse', 70.00, 220.00),
(5, 'Creeping Dusk', 115.30, 250.70),
(6, 'Deep Sky Abyss', 150.00, 280.00),
(7, 'Abyssal Rebound', 185.00, 250.00),
(8, 'Flickering Eclipse', 230.40, 220.30),
(9, 'Planar Slingshot', 285.00, 280.00),
(10, 'Oscillating Drift', 260.00, 140.00),
(11, 'Equilibrium Crossing', 210.00, 60.00),
(12, 'Second Dawn', 150.00, 25.00),
(13, 'Wobble East', 180.20, 50.30),
(14, 'Planar Distortion', 240.00, 120.00),
(15, 'Shattered Zenith', 289.60, 250.20),
(16, 'Nadir Bounce', 220.30, 210.40),
(17, 'Void Crossing', 180.00, 270.00),
(18, 'Southern Abyss', 150.00, 290.00),
(19, 'Retrograde Warp', 95.40, 240.00),
(20, 'Ecliptic Bounce', 45.00, 150.00),
(21, 'Horizon Dip', 15.00, 95.00),
(22, 'Pre-Dawn Flare', 55.00, 40.00),
(23, 'Twilight Descent', 105.00, 30.00)
ON CONFLICT (segment_id) DO NOTHING;

-- ============================================================================
-- 7. PLAYER SAGA STACK
-- ============================================================================
-- Tracks asynchronous gameplay events and choices for narrative generation.
CREATE TABLE player_saga_stack (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID NOT NULL REFERENCES player_characters(character_id) ON DELETE CASCADE,
    target_cell_id BIGINT NOT NULL REFERENCES global_simulation_cells(cell_id) ON DELETE CASCADE,
    event_type VARCHAR(255) NOT NULL,
    stat_used VARCHAR(100),
    roll_result INTEGER,
    context_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_player_saga_stack_char_recorded ON player_saga_stack (character_id, recorded_at);\n-- ============================================================================
-- 8. HYBRID VECTOR LORE INFRASTRUCTURE
-- ============================================================================

-- Try to create the vector extension
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'pgvector extension not available, setting up custom array-based operator fallback.';
END;
$$;

-- Conditional table and index setup based on pgvector existence
DO $$
DECLARE
    vector_type_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'vector'
    ) INTO vector_type_exists;

    -- Drop old ledger table if it exists to clean up column changes
    DROP TABLE IF EXISTS campaign_lore_ledger CASCADE;
    DROP TABLE IF EXISTS vectorized_world_lore CASCADE;

    IF vector_type_exists THEN
        -- Create table with vector type
        EXECUTE '
        CREATE TABLE campaign_lore_ledger (
            ledger_id SERIAL PRIMARY KEY,
            associated_cell_id BIGINT REFERENCES global_simulation_cells(cell_id) ON DELETE CASCADE,
            faction_tag VARCHAR(100) NOT NULL,
            raw_history_summary TEXT NOT NULL,
            semantic_lore_embedding vector(1536) NOT NULL,
            recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );';
        
        EXECUTE '
        CREATE TABLE vectorized_world_lore (
            lore_id SERIAL PRIMARY KEY,
            source_file_name VARCHAR(255) NOT NULL,
            target_faction VARCHAR(100) NOT NULL,
            geographic_tags VARCHAR(100)[] NOT NULL,
            raw_lore_text TEXT NOT NULL,
            lore_embedding vector(1536) NOT NULL,
            recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );';
        
        -- Create HNSW indices
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_lore_ledger_hnsw ON campaign_lore_ledger USING hnsw (semantic_lore_embedding vector_cosine_ops);';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_world_lore_hnsw ON vectorized_world_lore USING hnsw (lore_embedding vector_cosine_ops);';
    ELSE
        -- Create custom functions for REAL[] fallback
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

        -- Create operator if not exists
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

        -- Create table with REAL[] type fallback
        EXECUTE '
        CREATE TABLE campaign_lore_ledger (
            ledger_id SERIAL PRIMARY KEY,
            associated_cell_id BIGINT REFERENCES global_simulation_cells(cell_id) ON DELETE CASCADE,
            faction_tag VARCHAR(100) NOT NULL,
            raw_history_summary TEXT NOT NULL,
            semantic_lore_embedding REAL[] NOT NULL,
            recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );';

        EXECUTE '
        CREATE TABLE vectorized_world_lore (
            lore_id SERIAL PRIMARY KEY,
            source_file_name VARCHAR(255) NOT NULL,
            target_faction VARCHAR(100) NOT NULL,
            geographic_tags VARCHAR(100)[] NOT NULL,
            raw_lore_text TEXT NOT NULL,
            lore_embedding REAL[] NOT NULL,
            recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );';

        -- Standard indices for fallback columns
        CREATE INDEX IF NOT EXISTS idx_lore_ledger_cell_id ON campaign_lore_ledger (associated_cell_id);
        CREATE INDEX IF NOT EXISTS idx_world_lore_faction ON vectorized_world_lore (target_faction);
    END IF;
END;
$$;\n

-- ============================================================================
-- SEED DATA FOR REGISTRIES (FACTIONS, FLORA, FAUNA)
-- ============================================================================

-- Seed Faction Registry with Core and Unique Lore Factions
INSERT INTO registry_factions (faction_name, ideology_type, reputation_baseline) VALUES
('#GorgonHorde', 'Expansionist', 0),
('#CinderClaw', 'Survivalist', 0),
('#IronClan', 'Industrialist', 0),
('#Independent', 'Neutral', 0),
('#GreyWardens', 'Vigilant Guardians', 50),
('#CrimsonCorsairs', 'Rebellion Sky-Pirates', -30),
('#CloudHarriers', 'Aerostatic Raiders', -20),
('#OrderOfClockwork', 'Determined Bureaucrats', 30),
('#Hearthless', 'Planar Outcasts', -10),
('#CanalKrewes', 'Urban Trade Cartel', 15)
ON CONFLICT (faction_name) DO UPDATE SET
  ideology_type = EXCLUDED.ideology_type,
  reputation_baseline = EXCLUDED.reputation_baseline;

-- Seed Flora Registry with Generic and Unique Lore Plants
INSERT INTO registry_flora (scientific_name, common_name, temp_preference_min, temp_preference_max, moisture_preference_min, moisture_preference_max, growth_rate_modifier) VALUES
('ryegrass', 'Steppe Ryegrass', 5.00, 30.00, 0.200, 0.600, 1.00),
('broadleaf_oak', 'Broadleaf Oak', 10.00, 25.00, 0.350, 0.750, 1.00),
('pine', 'Boreal Pine', -15.00, 15.00, 0.200, 0.600, 0.80),
('alpine_moss', 'Alpine Moss', -25.00, 5.00, 0.100, 0.500, 0.50),
('saguaro_cactus', 'Saguaro Cactus', 15.00, 45.00, 0.000, 0.150, 0.60),
('rainforest_fern', 'Rainforest Fern', 18.00, 35.00, 0.700, 1.000, 1.30),
('mangrove', 'Bayou Mangrove', 15.00, 30.00, 0.650, 0.950, 1.10),
('aether_root', 'Aetheric Root Glow', 5.00, 25.00, 0.300, 0.800, 1.20),
('cinder_bloom', 'Ashen Cinder Bloom', 20.00, 50.00, 0.050, 0.300, 0.75),
('medicinal_herb', 'Sanative Sage', 8.00, 28.00, 0.250, 0.650, 1.00),
('dragonstone_vine', 'Dragonstone Vine', 12.00, 32.00, 0.300, 0.700, 1.10),
('silver_leaf', 'Scholarly Silver Leaf', 10.00, 22.00, 0.400, 0.700, 0.90),
('jolt_berry', 'Voltaic Jolt Berry', 10.00, 30.00, 0.300, 0.800, 1.15),
('ozone_flower', 'High-Altitude Ozone Flower', -10.00, 20.00, 0.200, 0.600, 1.05)
ON CONFLICT (scientific_name) DO UPDATE SET
  common_name = EXCLUDED.common_name,
  temp_preference_min = EXCLUDED.temp_preference_min,
  temp_preference_max = EXCLUDED.temp_preference_max,
  moisture_preference_min = EXCLUDED.moisture_preference_min,
  moisture_preference_max = EXCLUDED.moisture_preference_max,
  growth_rate_modifier = EXCLUDED.growth_rate_modifier;

-- Seed Fauna Registry with Generic and Unique Lore Wildlife
INSERT INTO registry_fauna (scientific_name, common_name, dietary_classification, base_pack_size, reproduction_rate) VALUES
('steppe_gazelle', 'Steppe Gazelle', 'Herbivore', 12, 1.10),
('red_deer', 'Stately Red Deer', 'Herbivore', 8, 0.90),
('boreal_elk', 'Boreal Elk', 'Herbivore', 6, 0.80),
('mountain_goat', 'Alpine Mountain Goat', 'Herbivore', 4, 0.70),
('desert_viper', 'Arid Desert Viper', 'Carnivore', 1, 1.20),
('tree_frog', 'Emerald Tree Frog', 'Insectivore', 25, 2.10),
('reef_fish', 'Coastal Reef Fish', 'Omnivore', 50, 2.50),
('abyssal_eel', 'Abyssal Deep Eel', 'Carnivore', 2, 0.50),
('polar_bear', 'Arctic Polar Bear', 'Carnivore', 1, 0.30),
('lynx', 'Boreal Lynx', 'Carnivore', 2, 0.60),
('red_fox', 'Sly Red Fox', 'Omnivore', 2, 1.15),
('jaguar', 'Jungle Jaguar', 'Carnivore', 1, 0.45),
('swamp_leech', 'Bloody Swamp Leech', 'Carnivore', 100, 3.50),
('caiman', 'Estuary Caiman', 'Carnivore', 3, 0.75),
('dragonstone_wasp', 'Swarming Magitech Wasp', 'Insectivore', 30, 2.00),
('cloud_harrier', 'Aerostatic Cloud Harrier', 'Carnivore', 4, 0.70),
('seahorse_courier', 'Trained Seahorse Courier', 'Herbivore', 3, 1.00),
('spring_ghost', 'Spectral Spring Ghost', 'Detritivore', 1, 0.20),
('voltaic_sheep', 'Static Fleece Sheep', 'Herbivore', 10, 1.00),
('wind_hawk', 'Shattered Peak Wind Hawk', 'Carnivore', 2, 0.85)
ON CONFLICT (scientific_name) DO UPDATE SET
  common_name = EXCLUDED.common_name,
  dietary_classification = EXCLUDED.dietary_classification,
  base_pack_size = EXCLUDED.base_pack_size,
  reproduction_rate = EXCLUDED.reproduction_rate;
