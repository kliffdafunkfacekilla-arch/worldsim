import os
import re
import json
import logging
from typing import Dict, Any, List, Optional
import asyncpg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lore_pipeline")

async def ingest_obsidian_vault(db_pool: asyncpg.Pool, vault_path: str) -> tuple:
    """
    Scans the local directory recursively, parsing markdown frontmatter,
    splitting content by '---' markers, extracting metadata, generating 1536-dimensional
    embeddings, and inserting them into the vectorized_world_lore table.
    """
    logger.info(f"Ingestion Hook: Scanning Obsidian vault at '{vault_path}'...")
    
    if not os.path.exists(vault_path):
        logger.error(f"Ingestion Hook: Vault directory '{vault_path}' does not exist!")
        return 0, 0
        
    from narrative_quest_engine import generate_text_embedding
    
    md_files = []
    for root, dirs, files in os.walk(vault_path):
        for file in files:
            if file.endswith(".md"):
                md_files.append(os.path.join(root, file))
                
    if not md_files:
        logger.warning(f"Ingestion Hook: No markdown files found under '{vault_path}'.")
        return 0, 0

    total_chunks = 0
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # Truncate existing lore table to avoid duplication
            await conn.execute("TRUNCATE TABLE vectorized_world_lore;")
            
            for file_path in md_files:
                basename = os.path.basename(file_path)
                logger.info(f"Processing chronicle: {basename}")
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as read_err:
                    logger.error(f"Failed to read file {basename}: {read_err}")
                    continue
                    
                # Separate YAML frontmatter and markdown body
                body = content
                frontmatter = {}
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        body = parts[2]
                        # Parse simple frontmatter keys
                        for line in parts[1].splitlines():
                            if ":" in line:
                                k, v = line.split(":", 1)
                                frontmatter[k.strip().lower()] = v.strip()
                
                # Split body into sections using "---" as delimiter
                chunks = [c.strip() for c in body.split("---")]
                if not chunks or (len(chunks) == 1 and not chunks[0]):
                    chunks = [body.strip()]
                    
                for chunk in chunks:
                    if not chunk or len(chunk) < 20:
                        continue # Skip trivial or empty dividers
                        
                    # Extract target faction from chunk or frontmatter
                    # Factions: #GorgonHorde, #CinderClaw, #IronClan, #Independent
                    faction_match = re.search(r"#GorgonHorde|#CinderClaw|#IronClan|#Independent", chunk)
                    target_faction = faction_match.group(0) if faction_match else frontmatter.get("target_faction", "#Independent")
                    
                    # Extract geographic tags (coordinates, biomes, active tags)
                    geo_tags = []
                    # 1. Capture coordinates e.g. (100, 100) or (150, 150)
                    coords = re.findall(r"\(\d+,\s*\d+\)", chunk)
                    geo_tags.extend(coords)
                    
                    # 2. Capture active chaos tags (#Flux, #Vita, #Mass, #StableReality)
                    tags = re.findall(r"#[A-Za-z0-9_]+", chunk)
                    for tag in tags:
                        if tag not in ["#GorgonHorde", "#CinderClaw", "#IronClan", "#Independent"] and tag not in geo_tags:
                            geo_tags.append(tag)
                            
                    # Generate 1536-dimensional embedding
                    embedding = generate_text_embedding(chunk, 1536)
                    
                    # Insert into vectorized_world_lore
                    await conn.execute(
                        """
                        INSERT INTO vectorized_world_lore (source_file_name, target_faction, geographic_tags, raw_lore_text, lore_embedding)
                        VALUES ($1, $2, $3, $4, $5);
                        """,
                        basename, target_faction, geo_tags, chunk, embedding
                    )
                    total_chunks += 1
                    
    logger.info(f"Ingestion Hook: Successfully loaded {len(md_files)} files generating {total_chunks} lore records.")
    return len(md_files), total_chunks


async def query_hybrid_campaign_lore(conn: asyncpg.Connection, query_embedding: List[float], faction_tag: str, associated_cell_id: int) -> List[dict]:
    """
    CRITICAL HYBRID LOGIC: Filters records first by relational keys (faction_tag AND cell_id),
    then sorts the remaining subset using pgvector's cosine distance operator (<=>).
    """
    logger.info(f"Hybrid Query: Relational filter (faction={faction_tag}, cell={associated_cell_id}) + Vector distance search...")
    rows = await conn.fetch(
        """
        SELECT ledger_id, associated_cell_id, faction_tag, raw_history_summary, recorded_at,
               (semantic_lore_embedding <=> $1) AS cosine_dist
        FROM campaign_lore_ledger
        WHERE faction_tag = $2 AND associated_cell_id = $3
        ORDER BY cosine_dist ASC
        LIMIT 3;
        """,
        query_embedding, faction_tag, associated_cell_id
    )
    return [dict(r) for r in rows]


async def query_hybrid_world_lore(conn: asyncpg.Connection, query_embedding: List[float], target_faction: str) -> List[dict]:
    """
    Searches parsed Obsidian lore files matching the targeted faction using the <=> distance operator.
    """
    logger.info(f"Hybrid Query: World Lore search (faction={target_faction}) + Vector distance search...")
    rows = await conn.fetch(
        """
        SELECT lore_id, source_file_name, target_faction, geographic_tags, raw_lore_text, recorded_at,
               (lore_embedding <=> $1) AS cosine_dist
        FROM vectorized_world_lore
        WHERE target_faction = $2
        ORDER BY cosine_dist ASC
        LIMIT 3;
        """,
        query_embedding, target_faction
    )
    return [dict(r) for r in rows]
