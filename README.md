# Planetary Simulation Engine & Tactical Sandbox

An asynchronous planetary-scale simulation engine featuring localized civilization expansion, geopolitics, and a tactical resolution sandbox built on the B.R.U.T.A.L. Engine rule system.

## Project Architecture

The simulation is split into a high-performance asynchronous FastAPI backend hub and a Kivy desktop client:

*   **`main.py`**: The core FastAPI simulation server, exposing API endpoints for cell profiles, map grids, player character updates, and tactical resolutions.
*   **`main_client.py`**: The main Kivy viewport and HUD client.
*   **`quad_nested_client.py`**: A specialized Kivy desktop client implementing the 4-tier Nested Planetary Coordinate Engine (Continental, Regional, Screen, Tile) with cascading overflow/underflow logic and asynchronous server API handshakes.
*   **`rpg_stat_core.py`**: The tactical B.R.U.T.A.L. Engine module. Calculates dynamic capacity pools based on clamped 2-8 scale attributes, derived sub-stats, gear taxes, contested clash tactic resolutions, and chaos channelling.
*   **`narrative_quest_engine.py`**: Procedural quest assembler with history-based saga stack twists.
*   **`civ_expansion_engine.py`**: Handles daily civilization ticks, localized emergencies (Refugee Camps and States of Emergency), faction doctrines, and rebel insurgencies.
*   **`chaos_orbit_engine.py` / `persistency_manager.py`**: Coordinates hourly decay sweeping of floor items and bodies.
*   **`crust_seeder.py`**: Seeds the 300x300 planetary grid terrain details.

## Rule System: The B.R.U.T.A.L. Engine

The tactical sandbox utilizes the custom B.R.U.T.A.L. Engine rule system:
1.  **The 2-8 Stat Scale**: Compressed scale where 3 is biological average and 4-6 is player-level expertise.
2.  **Chassis Capacities**: Token-based resource pools computed directly from attributes:
    *   `Max Health` = Endurance + Fortitude + Vitality
    *   `Max Stamina` = Might + Reflexes + Finesse
    *   `Max Composure` = Willpower + Logic + Charm
    *   `Max Focus` = Knowledge + Awareness + Intuition
3.  **Derived Sub-Stats**: Synthesizes stats into `Perception` (declaration order), `Stealth & Camo`, `Movement & Speed` (execution priority), and `Balance`.
4.  **Gear Tax & Systemic Overload**: Deducts weapon/armor tiers (Light=-1, Medium=-2, Heavy=-3) from Max Stamina/Focus pools, offset by passive hardware tracks (+1 for Tier 2, +2 for Tier 6). Throttles token regeneration from 2 to 1 if modified tax exceeds 50% max pool capacity.
5.  **Clash Contested Ties**: On exact d20 ties, deducts 1 Stamina and 1 Focus token from both entities. Evaluates outcomes using the 6-tactic matrix (`Press`, `Hold`, `Maneuver`, `Trick`, `Feint`, `Disengage`).
6.  **Reserve Burns & Chaos**: Acting with 0 resource tokens forces "Channel the Chaos" (d100 roll vs personal exposure). Success doubles action effect and raises exposure; failure triggers a localized Wild Resonance. Exposure > 90.0 forces physical mutations.
7.  **Atomic Transaction Security**: Client updates are committed immediately to the PostgreSQL database (`POST /api/player/update-pools`) to guarantee durability and prevent desyncs.

## Installation & Running

### Prerequisites
*   Python 3.10+
*   PostgreSQL database (configured via `DATABASE_URL` environment variable)

### Running the Server
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### Running the Kivy Client
```bash
python quad_nested_client.py
```
