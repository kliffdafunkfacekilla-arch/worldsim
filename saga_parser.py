import os
import json
import asyncio
import argparse
import logging
from uuid import UUID
import asyncpg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("saga_parser")

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:PigPig3897!!@localhost:5432/worldsim")

# Ensure Obsidian Vault Chronicles directory exists
VAULT_DIR = os.path.join(os.getcwd(), "your_design_vault", "Chronicles")

def generate_narrative(
    character_name: str,
    event_type: str,
    stat_used: str,
    roll_result: int,
    ambient_metrics: dict,
    gameplay_choices: dict
) -> str:
    """
    Generates an evocative, fantasy-themed narrative prose based on the event details,
    the character's checked stat, the roll result, and the surrounding environment.
    Strictly adheres to the fantasy setting and avoids D&D terminology.
    """
    # 1. Determine geographic description
    elevation = ambient_metrics.get("elevation_meters") or 0.0
    temp = ambient_metrics.get("temperature_celsius") or 15.0
    moisture = ambient_metrics.get("moisture_index") or 0.5
    coord_x = ambient_metrics.get("coord_x")
    coord_y = ambient_metrics.get("coord_y")

    geo_desc = ""
    if elevation < 0.0:
        geo_desc = "deep within the dark, pressure-choked ocean depths"
    elif elevation > 2000.0:
        geo_desc = "high upon the frozen, wind-scoured mountain peaks"
    else:
        if moisture < 0.2:
            geo_desc = "across the arid, shifting dunes of the dry wastes"
        elif moisture > 0.8:
            geo_desc = "through the humid, tangled thickets of the primeval jungle"
        else:
            geo_desc = "across the rolling grasslands and temperate forests"

    # Temperature overlay
    temp_desc = ""
    if temp < 0.0:
        temp_desc = "under a biting, sub-zero chill"
    elif temp > 35.0:
        temp_desc = "under a scorching, oppressive heat"
    else:
        temp_desc = "under a mild and shifting sky"

    # Faction and tier context
    faction = ambient_metrics.get("faction") or "#Independent"
    tier = ambient_metrics.get("tier") or "Wilderness"
    
    loc_desc = f"at coordinates ({coord_x}, {coord_y}), a region known as a {tier}"
    if faction != "#Independent":
        loc_desc += f" under the sovereign banner of {faction}"
    else:
        loc_desc += " untouched by faction banners"

    # 2. Chaos tag influence
    chaos_tag = ambient_metrics.get("active_chaos_tag") or "StableReality"
    chaos_desc = ""
    if "#Vita" in chaos_tag:
        chaos_desc = "The surrounding flora pulsed with wild, hyper-regenerative growth, vines splitting stone in a chaotic display of raw life energy."
    elif "#Mass" in chaos_tag:
        chaos_desc = "A crushing gravitational force weighed down on the landscape, making every movement heavy and labored."
    elif "#Flux" in chaos_tag:
        chaos_desc = "The planar fabric shimmered with volatile mutation magic, distorting light and reshaping materials unpredictably."
    elif "#Ordo" in chaos_tag:
        chaos_desc = "An eerie, geometric stillness held the area in a rigid lock, as if the planar laws themselves were freezing all change."
    elif "StableReality" in chaos_tag or not chaos_tag or chaos_tag == "None":
        chaos_desc = "The laws of reality held firm, offering a stable and predictable backdrop."
    else:
        # Fallback for other custom chaos tags
        chaos_desc = f"The planar landscape hummed with the resonance of the {chaos_tag} force."

    # 3. Shadow war atmosphere
    cult_index = ambient_metrics.get("cult_infiltration_index") or 0.0
    warden_presence = ambient_metrics.get("warden_presence") or 0.0
    shadow_desc = ""
    if cult_index > 0.5:
        shadow_desc = "Whispers of shadowed paranoia and hidden corruption lingered in the cold wind."
    elif warden_presence > 0.5:
        shadow_desc = "Silent protective wards hummed nearby, signaling the vigilant presence of the Wardens."

    # 4. Stat and Roll interpretation
    stat_phrase = ""
    if stat_used:
        stat_name = stat_used.lower()
        if stat_name == "might":
            stat_phrase = "relying on raw physical power and muscle"
        elif stat_name == "endurance":
            stat_phrase = "pushing the limits of physical stamina and hardiness"
        elif stat_name == "finesse":
            stat_phrase = "utilizing precise coordination and dexterous grace"
        elif stat_name == "reflex":
            stat_phrase = "relying on lightning-fast reflexes and reaction times"
        elif stat_name == "vitality":
            stat_phrase = "drawing from the depths of inner life force"
        elif stat_name == "fortitude":
            stat_phrase = "standing firm against planar feedback and mental fatigue"
        elif stat_name == "knowledge":
            stat_phrase = "recalling ancient historical lore and planar patterns"
        elif stat_name == "logic":
            stat_phrase = "solving the complex puzzle with analytical reason"
        elif stat_name == "awareness":
            stat_phrase = "sensing subtle movements and environmental shifts"
        elif stat_name == "intuition":
            stat_phrase = "heeding a sudden, inexplicable premonition"
        elif stat_name == "charm":
            stat_phrase = "weaving words of persuasive grace and command"
        elif stat_name == "willpower":
            stat_phrase = "asserting mental dominance and absolute resolve"
        else:
            stat_phrase = f"drawing upon the character's {stat_name}"

    # Outcome levels
    outcome_desc = ""
    if roll_result is not None:
        if roll_result >= 15:
            outcome_desc = f"met with stellar triumph. A roll of {roll_result} yielded a flawless victory."
        elif roll_result >= 10:
            outcome_desc = f"succeeded. A roll of {roll_result} secured a solid, reliable resolution."
        else:
            outcome_desc = f"struggled. A roll of {roll_result} led to a difficult setback or complicated compromise."
    else:
        outcome_desc = "unfolded without a formal roll of the dice."

    # 5. Core Event Narratives
    event_prose = ""
    if event_type == "LANDMARK_DISCOVERY":
        if roll_result is not None and roll_result >= 10:
            event_prose = (
                f"{character_name} uncovered an ancient planetary landmark hidden from modern maps. "
                "The air hummed with dormant power as the character traced the structural carvings, "
                "deciphering their long-lost history."
            )
        else:
            event_prose = (
                f"{character_name} stumbled upon the weathered remains of an old monument. "
                "Though half-buried and silent, it served as a stark reminder of the planar forces "
                "that once shaped this region."
            )
    elif event_type == "SHADOW_CONFRONTATION":
        if roll_result is not None and roll_result >= 10:
            event_prose = (
                f"{character_name} confronted a localized gathering of the hidden Chaos Cult. "
                "By remaining steady and acting decisively, they successfully disrupted the cultists' "
                "ritual, forcing them back into the shadows."
            )
        else:
            event_prose = (
                f"{character_name} walked into a carefully laid ambush by the cultists. "
                "Only through desperate maneuvering did they manage to escape the dark energies "
                "clutching at their shadow, leaving the area scarred by planar residue."
            )
    elif event_type == "REACTION_MELTDOWN":
        if roll_result is not None and roll_result >= 10:
            event_prose = (
                f"As the local magitech reactor began to overload, {character_name} intervened. "
                "By carefully venting the pressurized magical radiation and locking down the core, "
                "they averted a catastrophic explosion."
            )
        else:
            event_prose = (
                f"The magitech reactor ruptured, triggering a meltdown. {character_name} was forced "
                "to flee as planar radiation washed over the cell, permanently warping the landscape "
                "and leaving wild abominations in its wake."
            )
    elif event_type == "FACTION_SKIRMISH":
        if roll_result is not None and roll_result >= 10:
            event_prose = (
                f"Caught in a border skirmish, {character_name} rallied the defensive ranks. "
                "Through swift action, they repelled the enemy scouts and secured the settlement's perimeter."
            )
        else:
            event_prose = (
                f"A sudden clash between rival factions caught {character_name} in the crossfire. "
                "They were forced to fall back as the outpost was overrun and engulfed in conflict."
            )
    elif event_type == "WILDERNESS_TRAVEL":
        if roll_result is not None and roll_result >= 10:
            event_prose = (
                f"Navigating the pathless wilds, {character_name} found a safe path. "
                "They avoided treacherous ravines and navigated around nests of dangerous local predators."
            )
        else:
            event_prose = (
                f"The wild terrain proved treacherous. {character_name} lost the trail in the heavy mist, "
                "wandering through toxic flora and exhausting their energy reserves before finding the way."
            )
    else:
        # Fallback event narrative
        event_prose = (
            f"{character_name} engaged in a significant challenge: {event_type}. "
            "They navigated the immediate obstacles of the environment, attempting to influence the course of local history."
        )

    # 6. Weave choices if present
    choice_desc = ""
    if gameplay_choices:
        choice_desc = " Choosing to " + ", ".join(f"{k} ({v})" for k, v in gameplay_choices.items()) + "."

    # 7. Assemble the final story
    story = (
        f"Traveling {geo_desc} {temp_desc}, {character_name} found themselves {loc_desc}. "
        f"{chaos_desc} {shadow_desc} Here, the hero faced a challenge of {event_type}, "
        f"{stat_phrase if stat_phrase else 'relying on instinct'}. This effort {outcome_desc}"
        f"{choice_desc} {event_prose}"
    )
    return story

async def initialize_chronicle_file(filepath: str, character_id: UUID, character_name: str):
    """
    Initializes the Chronicle Markdown file with Obsidian-friendly YAML frontmatter.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    frontmatter = f"""---
character_id: {character_id}
character_name: {character_name}
type: Chronicle
---
# Saga Chronicle: {character_name}

An enduring chronicle of deeds, planar alignments, and historical struggles across the simulation.

"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter)
    logger.info(f"Initialized new chronicle file for {character_name} at {filepath}")

async def process_character_saga(conn, character_id: UUID, character_name: str) -> int:
    """
    Queries, formats, and deletes unprocessed events for a specific character.
    Processes the entire queue inside an atomic transaction.
    """
    # 1. Query all unprocessed events for this character in FIFO order
    rows = await conn.fetch(
        """
        SELECT event_id, target_cell_id, event_type, stat_used, roll_result, context_payload, recorded_at
        FROM player_saga_stack
        WHERE character_id = $1
        ORDER BY recorded_at ASC;
        """,
        character_id
    )

    if not rows:
        logger.info(f"No unprocessed events found for character {character_name} ({character_id}).")
        return 0

    event_ids = [row["event_id"] for row in rows]
    filepath = os.path.join(VAULT_DIR, f"{character_name}_Chronicle.md")

    # Ensure file exists and is initialized
    if not os.path.exists(filepath):
        await initialize_chronicle_file(filepath, character_id, character_name)

    # 2. Open the file to append new narrative blocks
    markdown_blocks = []
    for row in rows:
        payload = row["context_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        system_clock = payload.get("system_clock") or {"current_year": 1, "current_day": 1, "current_segment": 0}
        ambient = payload.get("ambient_metrics") or {}
        choices = payload.get("gameplay_choices") or {}

        year = system_clock.get("current_year", 1)
        day = system_clock.get("current_day", 1)
        segment = system_clock.get("current_segment", 0)

        # Generate the evocative narrative prose
        narrative = generate_narrative(
            character_name=character_name,
            event_type=row["event_type"],
            stat_used=row["stat_used"],
            roll_result=row["roll_result"],
            ambient_metrics=ambient,
            gameplay_choices=choices
        )

        block = f"""### Year {year}, Day {day}, Segment {segment} — {row['event_type']}
- **Location**: Coordinate `({ambient.get('coord_x', '?')}, {ambient.get('coord_y', '?')})` | Tier: `{ambient.get('tier', 'Wilderness')}` | Faction: `{ambient.get('faction', '#Independent')}`
- **Planar Climate**: Elevation: `{ambient.get('elevation_meters', 0.0)}m` | Temperature: `{ambient.get('temperature_celsius', 15.0)}°C` | Moisture: `{ambient.get('moisture_index', 0.5)}` | Chaos Alignment: `{ambient.get('active_chaos_tag', 'StableReality')}`
- **Action**: Tested **{row['stat_used'] or 'Instinct'}** (Roll result: `{row['roll_result'] if row['roll_result'] is not None else 'N/A'}`)
- **Chronicle entry**:
  > {narrative}

---
"""
        markdown_blocks.append(block)

    # 3. Append to file
    with open(filepath, "a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(markdown_blocks))
    logger.info(f"Appended {len(markdown_blocks)} chronicle entry blocks to {filepath}.")

    # 4. Clean up queue in database
    await conn.execute(
        "DELETE FROM player_saga_stack WHERE event_id = ANY($1::uuid[]);",
        event_ids
    )
    logger.info(f"Deleted {len(event_ids)} processed event rows from player_saga_stack queue.")
    return len(event_ids)

async def main():
    parser = argparse.ArgumentParser(description="Processes player saga stack and outputs to Obsidian Chronicles.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--character-id", type=str, help="UUID of the character to process.")
    group.add_argument("--character-name", type=str, help="Name of the character to process.")
    
    args = parser.parse_args()

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Resolve character details
        character_id = None
        character_name = None

        if args.character_id:
            try:
                char_uuid = UUID(args.character_id)
            except ValueError:
                logger.error(f"Invalid character-id format: {args.character_id}")
                return

            row = await conn.fetchrow(
                "SELECT character_id, character_name FROM player_characters WHERE character_id = $1;",
                char_uuid
            )
            if not row:
                logger.error(f"No character found with ID: {args.character_id}")
                return
            character_id = row["character_id"]
            character_name = row["character_name"]
        else:
            row = await conn.fetchrow(
                "SELECT character_id, character_name FROM player_characters WHERE character_name = $1;",
                args.character_name
            )
            if not row:
                logger.error(f"No character found with Name: {args.character_name}")
                return
            character_id = row["character_id"]
            character_name = row["character_name"]

        # Run process within a single database transaction
        async with conn.transaction():
            processed_count = await process_character_saga(conn, character_id, character_name)
            logger.info(f"Saga processing complete. {processed_count} events resolved.")

    except Exception as e:
        logger.exception("Error occurred while processing player saga:")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
