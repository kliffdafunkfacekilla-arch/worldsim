import os
import json
import uuid
import random
import logging
from typing import Dict, Any, List, Optional
import asyncpg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("narrative_quest_engine")

# DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:PigPig3897!!@localhost:5432/worldsim")

# Component Pools
QUEST_HOOKS = {
    "HK_01": {"title": "The Deserter's Confession", "objective": "Find the hidden stash in the ruins.", "theme": "general"},
    "HK_02": {"title": "A Whispered Conspiracy", "objective": "Meet the informant in the tavern.", "theme": "general"},
    "HK_03": {"title": "The Scorched Emblem", "objective": "Investigate the burned campsite.", "theme": "general"},
    "HK_04": {"title": "The Subversive Ledger", "objective": "Recover the cartel's secret codebook.", "theme": "cartel"}
}

QUEST_COMPLICATIONS = {
    "CP_01": {"description": "Ambush in the Mist", "objective": "Survive the sudden raider ambush.", "theme": "general"},
    "CP_02": {"description": "Planar Flux", "objective": "Stabilize the fluctuating mana rift.", "theme": "chaos"},
    "CP_03": {"description": "Cartel Enforcers", "objective": "Bypass or defeat the cartel patrol.", "theme": "cartel"},
    "CP_04": {"description": "Refugee Stampede", "objective": "Clear the blocked pathway safely.", "theme": "emergency"}
}

QUEST_CLIMAXES = {
    "CX_01": {"climax": "The Planar Breach", "objective": "Seal the active portal.", "theme": "chaos"},
    "CX_02": {"climax": "Showdown with the Warlord", "objective": "Defeat the enemy leader.", "theme": "general"},
    "CX_03": {"climax": "Destroy the Cult Altar", "objective": "Purify the defiled obelisk.", "theme": "cartel"},
    "CX_04": {"climax": "Reclaim the Sanctuary", "objective": "Defeat the abominations in the temple.", "theme": "emergency"}
}

class DynamicNarrativeEngine:
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url

    async def initialize_db(self, conn: asyncpg.Connection):
        """
        Creates the template_usage_tracker table if it does not exist.
        """
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS template_usage_tracker (
                component_id VARCHAR(100) PRIMARY KEY,
                usage_count INTEGER NOT NULL DEFAULT 0
            );
            """
        )

    async def get_usage_count(self, conn: asyncpg.Connection, component_id: str) -> int:
        count = await conn.fetchval(
            "SELECT usage_count FROM template_usage_tracker WHERE component_id = $1;",
            component_id
        )
        return count if count is not None else 0

    async def increment_usage(self, conn: asyncpg.Connection, component_id: str) -> int:
        new_count = await conn.fetchval(
            """
            INSERT INTO template_usage_tracker (component_id, usage_count)
            VALUES ($1, 1)
            ON CONFLICT (component_id) DO UPDATE 
            SET usage_count = template_usage_tracker.usage_count + 1
            RETURNING usage_count;
            """,
            component_id
        )
        return new_count

    async def reset_usage(self, conn: asyncpg.Connection, component_id: str):
        await conn.execute(
            "UPDATE template_usage_tracker SET usage_count = 0 WHERE component_id = $1;",
            component_id
        )

    async def generate_organic_story_seed(self, conn: asyncpg.Connection, character_id: uuid.UUID, cell_id: int) -> Dict[str, Any]:
        """
        Procedurally assembles a quest by picking a Hook, Complication, and Climax
        based on live simulation metrics. Applies structural mutations if component usage >= 3.
        """
        await self.initialize_db(conn)

        # 1. Fetch cell details for theme selection
        cell_row = await conn.fetchrow(
            """
            SELECT active_chaos_tag, shadow_war_metrics, civilization_profile 
            FROM global_simulation_cells WHERE cell_id = $1;
            """,
            cell_id
        )
        if not cell_row:
            raise ValueError(f"Cell {cell_id} not found in database.")

        active_tag = cell_row["active_chaos_tag"] or "#StableReality"
        shadow_metrics = cell_row["shadow_war_metrics"]
        civ_profile = cell_row["civilization_profile"]

        if isinstance(shadow_metrics, str):
            shadow_metrics = json.loads(shadow_metrics)
        else:
            shadow_metrics = shadow_metrics or {}

        if isinstance(civ_profile, str):
            civ_profile = json.loads(civ_profile)
        else:
            civ_profile = civ_profile or {}

        # Extract metrics
        subversion = float(shadow_metrics.get("subversion", shadow_metrics.get("cult_infiltration_index", 0.0)))
        tier = civ_profile.get("tier", "Wilderness")

        # Determine theme priority
        theme = "general"
        if subversion > 0.40:
            theme = "cartel"
        elif active_tag != "#StableReality" and active_tag != "":
            theme = "chaos"
        elif tier in ["Refugee_Camp", "State_of_Emergency"]:
            theme = "emergency"

        logger.info(f"Quest assembly for cell {cell_id} using theme: {theme} (subversion: {subversion}, tier: {tier}, active_tag: {active_tag})")

        # 2. Procedural selection based on theme
        # Hook selection
        hook_options = [k for k, v in QUEST_HOOKS.items() if v["theme"] == theme]
        if not hook_options:
            hook_options = [k for k, v in QUEST_HOOKS.items() if v["theme"] == "general"]
        hook_id = random.choice(hook_options)

        # Complication selection
        comp_options = [k for k, v in QUEST_COMPLICATIONS.items() if v["theme"] == theme]
        if not comp_options:
            comp_options = [k for k, v in QUEST_COMPLICATIONS.items() if v["theme"] == "general"]
        comp_id = random.choice(comp_options)

        # Climax selection
        climax_options = [k for k, v in QUEST_CLIMAXES.items() if v["theme"] == theme]
        if not climax_options:
            climax_options = [k for k, v in QUEST_CLIMAXES.items() if v["theme"] == "general"]
        climax_id = random.choice(climax_options)

        # Assemble chosen components
        components = [
            ("hook", hook_id, dict(QUEST_HOOKS[hook_id])),
            ("complication", comp_id, dict(QUEST_COMPLICATIONS[comp_id])),
            ("climax", climax_id, dict(QUEST_CLIMAXES[climax_id]))
        ]

        quest_components = {}
        mutations_triggered = []

        # 3. Check and apply Mutation Factor
        for comp_type, cid, comp_data in components:
            # Query usage count before increment
            usage = await self.get_usage_count(conn, cid)
            
            # Increment count
            new_usage = await self.increment_usage(conn, cid)
            
            is_mutated = False
            if usage >= 3:
                # Trigger Structural Mutation!
                is_mutated = True
                logger.info(f"MUTATION TRIGGERED for component {cid} (Usage: {usage})")
                
                # Fetch past historical saga action to construct twist
                past_events = await conn.fetch(
                    """
                    SELECT event_type, context_payload 
                    FROM player_saga_stack 
                    WHERE character_id = $1 
                    ORDER BY recorded_at DESC 
                    LIMIT 5;
                    """,
                    character_id
                )
                
                twist_objective = ""
                if past_events:
                    # Parse the sagaStack past action
                    evt = past_events[0]
                    evt_type = evt["event_type"]
                    payload = evt["context_payload"] or {}
                    choices = payload.get("gameplay_choices", {}) or {}
                    
                    actor = choices.get("actor", choices.get("target", choices.get("opponent", "a past adversary")))
                    action = choices.get("action", f"your past encounter in the event '{evt_type}'")
                    
                    twist_objective = f"SURPRISE TWIST: Forcefully confront '{actor}', who has returned because of your choice: '{action}'!"
                else:
                    twist_objective = "SURPRISE TWIST: Forcefully confront the rogue faction agent who resurfaced to sabotage you!"

                # Shift the Structure: Drop standard objective and personalize the twist
                comp_data["objective"] = twist_objective
                comp_data["mutated"] = True
                
                # Reset counter to 0
                await self.reset_usage(conn, cid)
                mutations_triggered.append(cid)
            else:
                comp_data["mutated"] = False

            comp_data["id"] = cid
            quest_components[comp_type] = comp_data

        # Combine into single fluid quest
        hook_obj = quest_components["hook"]
        comp_obj = quest_components["complication"]
        climax_obj = quest_components["climax"]

        quest_id = f"QST_{uuid.uuid4().hex[:8]}"
        quest_title = f"{hook_obj['title']}: {comp_obj['description']} to {climax_obj['climax']}"
        fluid_structure = (
            f"The quest begins when you encounter '{hook_obj['title']}'. "
            f"As you pursue this lead, you face a critical complication: '{comp_obj['description']}'. "
            f"Ultimately, your journey culminates in a final confrontation: '{climax_obj['climax']}'."
        )

        quest_result = {
            "quest_id": quest_id,
            "title": quest_title,
            "hook": hook_obj,
            "complication": comp_obj,
            "climax": climax_obj,
            "fluid_structure": fluid_structure,
            "mutations": mutations_triggered
        }
        
        logger.info(f"Quest assembled successfully: {quest_title} | Mutations: {mutations_triggered}")
        return quest_result
