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


class ParagonAIDirector:
    """
    Asynchronous Director that stages regional crises, uses a local LLM (or robust fallback)
    to roleplay autonomous Paragon decisions, maps intents to civilization profile changes,
    and inserts embedding-enabled lore records.
    """
    def __init__(self, db_pool: asyncpg.Pool, config: Dict[str, Any] = None):
        import asyncio
        self.db_pool = db_pool
        self.config = config or {}
        self.queue = asyncio.Queue()
        self.is_running = False

    def load_config(self) -> dict:
        config_path = "config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load config.json in ParagonAIDirector: {e}")
        return {}

    async def start(self):
        import asyncio
        if self.is_running:
            return
        self.is_running = True
        asyncio.create_task(self._director_loop())
        logger.info("Paragon AI Director worker started.")

    async def stop(self):
        self.is_running = False
        logger.info("Paragon AI Director worker stopped.")

    async def _director_loop(self):
        import asyncio
        while self.is_running:
            try:
                logger.info("ParagonAIDirector: Starting hourly crisis staging sweep...")
                # 1. Stage crises
                await self.stage_crises()
                
                # 2. Process queue during the downtime window (e.g. 50 minutes = 3000 seconds)
                downtime_duration = 3000
                start_time = asyncio.get_event_loop().time()
                
                processed_count = 0
                while not self.queue.empty():
                    event = await self.queue.get()
                    try:
                        await self.process_crisis_event(event)
                        processed_count += 1
                    except Exception as e:
                        logger.error(f"Error processing staged crisis: {e}")
                    # Throttle LLM calls to prevent thread/network spikes
                    await asyncio.sleep(5)
                
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining_sleep = max(10, downtime_duration - elapsed)
                logger.info(f"ParagonAIDirector: Processed {processed_count} crises. Sleeping for {remaining_sleep:.1f}s.")
                await asyncio.sleep(remaining_sleep)
                
            except Exception as e:
                logger.error(f"Error in ParagonAIDirector background loop: {e}")
                await asyncio.sleep(60)

    async def stage_crises(self):
        """
        Scans global_simulation_cells for aligned settlements with active crises.
        Scores and ranks them, then pushes up to 5 highest priority crises to the queue.
        """
        import asyncio
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT cell_id, coord_x, coord_y, civilization_profile, shadow_war_metrics, active_chaos_tag
                FROM global_simulation_cells
                WHERE (civilization_profile->>'faction' IS NOT NULL AND civilization_profile->>'faction' != '#Independent')
                   OR (civilization_profile->>'controlling_faction_id' IS NOT NULL);
                """
            )
            
            crises = []
            for row in rows:
                cell_id = row["cell_id"]
                coord_x = row["coord_x"]
                coord_y = row["coord_y"]
                active_tag = row["active_chaos_tag"]
                
                civ = row["civilization_profile"]
                if isinstance(civ, str):
                    civ = json.loads(civ)
                civ = civ or {}
                
                shadow = row["shadow_war_metrics"]
                if isinstance(shadow, str):
                    shadow = json.loads(shadow)
                shadow = shadow or {}
                
                # Exclude wilderness
                tier = civ.get("tier", "Wilderness")
                if tier == "Wilderness":
                    continue
                    
                score = 0.0
                
                # 1. Tier Severity
                if tier == "Refugee_Camp":
                    score += 5.0
                elif tier == "State_of_Emergency":
                    score += 10.0
                    
                # 2. Crime rate severity
                crime_rate = float(civ.get("crime_rate", 0.0))
                if crime_rate > 0.6:
                    score += (crime_rate - 0.6) * 10.0
                    
                # 3. Cartel saturation severity
                cartel_sat = float(civ.get("cartel_saturation", 0.0))
                if cartel_sat > 0.6:
                    score += (cartel_sat - 0.6) * 10.0
                    
                # 4. Happiness levels
                happiness = float(civ.get("happiness", 1.0))
                if happiness < 0.3:
                    score += (0.3 - happiness) * 15.0
                    
                # 5. Shadow unrest / subversion
                unrest = float(shadow.get("unrest", 0.0))
                if unrest > 0.5:
                    score += (unrest - 0.5) * 10.0
                    
                subversion = float(shadow.get("subversion", 0.0))
                if subversion > 0.5:
                    score += (subversion - 0.5) * 10.0
                    
                # 6. Active magic anomalies
                if active_tag and active_tag != "#StableReality":
                    score += 5.0
                    
                if score > 0.0:
                    crises.append({
                        "cell_id": cell_id,
                        "coord": (coord_x, coord_y),
                        "score": score,
                        "civ_profile": civ,
                        "shadow_metrics": shadow,
                        "active_tag": active_tag,
                        "tier": tier,
                        "crime_rate": crime_rate,
                        "subversion": subversion,
                        "unrest": unrest
                    })
            
            # Sort by priority score desc
            crises.sort(key=lambda x: x["score"], reverse=True)
            
            # Queue the top 5
            for c in crises[:5]:
                # Ensure there is a Paragon agent for this cell
                paragons = c["civ_profile"].get("paragons", [])
                if not paragons:
                    config = self.load_config()
                    # Lazy import to avoid circular dependency
                    from advanced_civilization_engine import generate_paragon_agent
                    new_p = generate_paragon_agent("Ruling Paragon", config)
                    paragons.append(new_p)
                    c["civ_profile"]["paragons"] = paragons
                    # Save back to database
                    await conn.execute(
                        "UPDATE global_simulation_cells SET civilization_profile = $1 WHERE cell_id = $2;",
                        json.dumps(c["civ_profile"]), c["cell_id"]
                    )
                
                # Pick the first Paragon for this roleplay
                paragon = paragons[0]
                
                # Initialize trauma_index and affiliations if missing
                paragon.setdefault("trauma_index", 0.0)
                faction = c["civ_profile"].get("faction") or c["civ_profile"].get("controlling_faction_id") or "#Independent"
                if "affiliations" not in paragon:
                    paragon["affiliations"] = [faction]
                elif faction not in paragon["affiliations"]:
                    paragon["affiliations"].append(faction)
                    
                c["paragon"] = paragon
                
                # Generate story seed based on crisis conditions
                if c["tier"] in ["Refugee_Camp", "State_of_Emergency"]:
                    story = "A desperate influx of refugees has overwhelmed local resources, causing food shortages and rising panic."
                elif c["crime_rate"] > 0.6:
                    story = "Local street gangs and cartel enforcers have seized control of the trade markets, defying the guards."
                elif c["subversion"] > 0.5:
                    story = "Whispering shadow cult rituals have sown distrust, and suspicious sigils are appearing on city walls."
                elif c["active_tag"] and c["active_tag"] != "#StableReality":
                    story = f"A reality-warping magical anomaly of type '{c['active_tag']}' is mutating the surrounding flora and destabilizing local ley lines."
                else:
                    story = "Civil unrest and severe resource strain are threatening the stability of the settlement."
                    
                c["story_seed"] = story
                await self.queue.put(c)
                logger.info(f"ParagonAIDirector: Queued crisis for cell {c['cell_id']} (score: {c['score']:.1f})")

    async def process_crisis_event(self, event: dict):
        """
        Executes LLM roleplay (or deterministic fallback) for a staged crisis,
        updates the civilization profile, and saves the embedding-enabled campaign lore.
        """
        cell_id = event["cell_id"]
        paragon = event["paragon"]
        story_seed = event["story_seed"]
        coord = event["coord"]
        faction = event["civ_profile"].get("faction") or event["civ_profile"].get("controlling_faction_id") or "#Independent"
        
        logger.info(f"ParagonAIDirector: Roleplaying crisis for Paragon {paragon['name']} in cell {cell_id}...")
        
        config = self.load_config()
        ai_cfg = config.get("ai_director_config", {})
        base_url = ai_cfg.get("llm_base_url", "http://localhost:11434/v1")
        model = ai_cfg.get("llm_model", "llama3")
        api_key = ai_cfg.get("llm_api_key", "local")
        
        prompt = f"""You are roleplaying as {paragon['name']}, a {paragon['role']} in the Shatterlands.
Your character profile:
- Personality Traits: {', '.join(paragon['traits'])}
- Personal Goals: {', '.join(paragon['personal_goals'])}
- Trauma Index: {paragon['trauma_index']}
- Affiliations: {', '.join(paragon['affiliations'])}

Local Settlement Context:
- Coordinates: {coord}
- Controlling Faction: {paragon['affiliations'][0]}

A regional crisis has emerged:
\"{story_seed}\"

As {paragon['name']}, decide on a single course of action to respond to this crisis. Your action must align with your psychological profile, goals, and affiliations.

You must respond with a JSON object inside a single code block matching the schema below:
{{
  \"decision_summary\": \"A brief text description of the action taken.\",
  \"mechanical_intent\": \"ATTACK_RIVAL\" | \"HOARD_RESOURCES\" | \"ALLY_WITH_CULT\" | \"STABILIZE_REGION\" | \"AID_REFUGEES\"
}}
Do not write any text outside of the JSON block."""
        
        decision_summary = ""
        mechanical_intent = ""
        
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                timeout=12.0
            )
            resp_content = response.choices[0].message.content.strip()
            if resp_content.startswith("```"):
                lines = resp_content.splitlines()
                if lines[0].startswith("```json"):
                    resp_content = "\n".join(lines[1:-1])
                else:
                    resp_content = "\n".join(lines[1:-1])
            
            parsed = json.loads(resp_content)
            decision_summary = parsed["decision_summary"]
            mechanical_intent = parsed["mechanical_intent"]
            
        except Exception as e:
            logger.warning(f"ParagonAIDirector: Local LLM failed ({e}). Running deterministic fallback.")
            fallback = self.fallback_roleplay_generator(paragon, story_seed)
            decision_summary = fallback["decision_summary"]
            mechanical_intent = fallback["mechanical_intent"]
            
        # Validate intent
        valid_intents = ["ATTACK_RIVAL", "HOARD_RESOURCES", "ALLY_WITH_CULT", "STABILIZE_REGION", "AID_REFUGEES"]
        if mechanical_intent not in valid_intents:
            mechanical_intent = "STABILIZE_REGION"
            
        logger.info(f"ParagonAIDirector: Resolved action '{mechanical_intent}' for {paragon['name']}")
        
        # Apply resolution to DB
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                # Lock row
                row = await conn.fetchrow(
                    "SELECT civilization_profile, shadow_war_metrics FROM global_simulation_cells WHERE cell_id = $1 FOR UPDATE;",
                    cell_id
                )
                if not row:
                    logger.error(f"Cell {cell_id} not found during resolution.")
                    return
                
                civ = row["civilization_profile"]
                if isinstance(civ, str):
                    civ = json.loads(civ)
                civ = civ or {}
                
                shadow = row["shadow_war_metrics"]
                if isinstance(shadow, str):
                    shadow = json.loads(shadow)
                shadow = shadow or {}
                
                # Make sure profile has basic keys
                civ.setdefault("security", 0.5)
                civ.setdefault("happiness", 0.5)
                civ.setdefault("crime_rate", 0.2)
                civ.setdefault("treasury", {"wealth": 100.0})
                if not isinstance(civ["treasury"], dict):
                    civ["treasury"] = {"wealth": float(civ["treasury"])}
                
                shadow.setdefault("subversion", 0.0)
                
                # Apply intent adjustments
                if mechanical_intent == "ATTACK_RIVAL":
                    civ["security"] = max(0.0, civ["security"] - 0.15)
                    civ["happiness"] = max(0.0, civ["happiness"] - 0.10)
                    civ["treasury"]["wealth"] = max(0.0, civ["treasury"].get("wealth", 0.0) - 25.0)
                elif mechanical_intent == "HOARD_RESOURCES":
                    civ["treasury"]["wealth"] = civ["treasury"].get("wealth", 0.0) + 50.0
                    civ["happiness"] = max(0.0, civ["happiness"] - 0.20)
                elif mechanical_intent == "ALLY_WITH_CULT":
                    civ["crime_rate"] = min(1.0, civ["crime_rate"] + 0.15)
                    shadow["subversion"] = min(1.0, shadow.get("subversion", 0.0) + 0.25)
                    civ["treasury"]["wealth"] = civ["treasury"].get("wealth", 0.0) + 40.0
                elif mechanical_intent == "STABILIZE_REGION":
                    civ["security"] = min(1.0, civ["security"] + 0.20)
                    civ["crime_rate"] = max(0.0, civ["crime_rate"] - 0.10)
                    civ["treasury"]["wealth"] = max(0.0, civ["treasury"].get("wealth", 0.0) - 20.0)
                elif mechanical_intent == "AID_REFUGEES":
                    civ["happiness"] = min(1.0, civ["happiness"] + 0.15)
                    civ["security"] = max(0.0, civ["security"] - 0.05)
                    civ["treasury"]["wealth"] = max(0.0, civ["treasury"].get("wealth", 0.0) - 30.0)
                
                # Save changes
                await conn.execute(
                    """
                    UPDATE global_simulation_cells
                    SET civilization_profile = $1, shadow_war_metrics = $2
                    WHERE cell_id = $3;
                    """,
                    json.dumps(civ), json.dumps(shadow), cell_id
                )
                
                # Generate embedding
                embedding = generate_text_embedding(decision_summary, 1536)
                
                # Write to ledger
                await conn.execute(
                    """
                    INSERT INTO campaign_lore_ledger (associated_cell_id, faction_tag, raw_history_summary, semantic_lore_embedding)
                    VALUES ($1, $2, $3, $4);
                    """,
                    cell_id, faction, f"{paragon['name']} ({paragon['role']}) responded to crisis: {decision_summary}", embedding
                )
                
        logger.info(f"ParagonAIDirector: Crisis resolved and lore ledger written for cell {cell_id}.")

    def fallback_roleplay_generator(self, paragon: dict, story_seed: str) -> dict:
        """
        Rule-based decision-making fallback when LLM is unavailable.
        Generates contextual decision descriptions and mapped intents based on traits/goals.
        """
        traits = [t.lower() for t in paragon.get("traits", [])]
        goals = [g.lower() for g in paragon.get("personal_goals", [])]
        name = paragon["name"]
        
        # Check traits
        if "greedy" in traits or "narcissistic" in traits:
            intent = "HOARD_RESOURCES"
            summary = f"{name} ordered a strict ration lock and increased regional taxes to secure the inner vault, prioritizing the treasury over refugee panic."
        elif "zealot" in traits or "ambitious" in traits:
            intent = "ATTACK_RIVAL"
            if "cult" in story_seed.lower():
                summary = f"{name} deployed elite templars and city squads to hunt down and purge suspected cult cells, locking down the lower quarters."
            else:
                summary = f"{name} launched a preemptive force sweep across the outskirts, clearing out unrest by force and detaining suspected troublemakers."
        elif "dutiful" in traits or "vigilant" in traits:
            intent = "STABILIZE_REGION"
            summary = f"{name} established safety barricades, doubled the city watch shifts, and coordinated with local neighborhood captains to secure key supply hubs."
        elif "calculating" in traits:
            # Check goals for decision
            if any("treasury" in g or "wealth" in g for g in goals):
                intent = "HOARD_RESOURCES"
                summary = f"{name} requisitioned local merchant storage containers, concentrating resources inside the central citadel to preserve economic assets."
            else:
                intent = "STABILIZE_REGION"
                summary = f"{name} calculated structural risk and ordered strategic patrols to contain the unrest in the poorest quarters."
        else:
            # Default by goal
            if any("stability" in g or "defend" in g for g in goals):
                intent = "STABILIZE_REGION"
                summary = f"{name} directed guards to establish order, calming the populace and securing key city gates."
            elif any("treasury" in g or "wealth" in g for g in goals):
                intent = "HOARD_RESOURCES"
                summary = f"{name} stockpiled essential grains and metals, setting limits on trade exports to safeguard internal reserves."
            else:
                intent = "AID_REFUGEES"
                summary = f"{name} opened auxiliary field kitchens and authorized emergency supply packages to alleviate civilian suffering."
                
        return {
            "decision_summary": summary,
            "mechanical_intent": intent
        }


def generate_text_embedding(text: str, dimension: int = 1536) -> List[float]:
    """
    Generates a 1536-dimensional unit vector embedding.
    Uses sentence-transformers if available and not forced to fallback,
    otherwise falls back to a deterministic text-hash based generator.
    """
    import hashlib
    import numpy as np
    
    # Check if fallback is forced via environment variable or config
    force_fallback = os.getenv("FORCE_EMBEDDING_FALLBACK", "0") == "1"
    if not force_fallback:
        config_path = "config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    cfg = json.load(f)
                    if cfg.get("ai_director_config", {}).get("force_embedding_fallback"):
                        force_fallback = True
            except:
                pass

    if not force_fallback:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            emb = model.encode(text)
            vec = list(emb)
            if len(vec) < dimension:
                vec.extend([0.0] * (dimension - len(vec)))
            return [float(x) for x in vec[:dimension]]
        except Exception:
            pass

    # Fallback to deterministic hash-based unit vector of size 1536
    h = hashlib.sha256(text.encode('utf-8')).digest()
    seed = int.from_bytes(h[:4], 'big')
    rng = np.random.default_rng(seed)
    vec = rng.normal(0, 1, dimension)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return [float(x) for x in vec]
