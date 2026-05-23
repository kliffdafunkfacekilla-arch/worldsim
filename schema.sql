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

CREATE INDEX idx_player_saga_stack_char_recorded ON player_saga_stack (character_id, recorded_at);
