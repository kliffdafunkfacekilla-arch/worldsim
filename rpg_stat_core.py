import random
from typing import Dict, List, Any, Optional, Tuple

MUTATION_POOL = [
    "Crystalline Scales",
    "Void Scarred Eyes",
    "Warped Silhouette",
    "Unstable Resonance",
    "Planar Phasing",
    "Mutated Maw",
    "Starlight Skin",
    "Tentacled Sinew"
]

CLASH_MATRIX = {
    # format: (tactic_a, tactic_b) -> outcome ("A_wins", "B_wins", or "tie")
    ("press", "press"): "tie",
    ("press", "hold"): "B_wins",      # Hold beats Press
    ("press", "maneuver"): "tie",
    ("press", "trick"): "A_wins",     # Press beats Trick
    ("press", "feint"): "A_wins",     # Press beats Feint
    ("press", "disengage"): "A_wins",  # Press beats Disengage
    
    ("hold", "press"): "A_wins",
    ("hold", "hold"): "tie",
    ("hold", "maneuver"): "B_wins",   # Maneuver beats Hold
    ("hold", "trick"): "A_wins",      # Hold beats Trick
    ("hold", "feint"): "B_wins",      # Feint beats Hold
    ("hold", "disengage"): "tie",
    
    ("maneuver", "press"): "tie",
    ("maneuver", "hold"): "A_wins",
    ("maneuver", "maneuver"): "tie",
    ("maneuver", "trick"): "A_wins",  # Maneuver beats Trick
    ("maneuver", "feint"): "B_wins",  # Feint beats Maneuver
    ("maneuver", "disengage"): "A_wins", # Maneuver beats Disengage
    
    ("trick", "press"): "B_wins",
    ("trick", "hold"): "B_wins",
    ("trick", "maneuver"): "B_wins",
    ("trick", "trick"): "tie",
    ("trick", "feint"): "A_wins",     # Trick beats Feint
    ("trick", "disengage"): "B_wins", # Disengage beats Trick
    
    ("feint", "press"): "B_wins",
    ("feint", "hold"): "A_wins",
    ("feint", "maneuver"): "A_wins",
    ("feint", "trick"): "B_wins",
    ("feint", "feint"): "tie",
    ("feint", "disengage"): "tie",
    
    ("disengage", "press"): "B_wins",
    ("disengage", "hold"): "tie",
    ("disengage", "maneuver"): "B_wins",
    ("disengage", "trick"): "A_wins",
    ("disengage", "feint"): "tie",
    ("disengage", "disengage"): "tie"
}

WILD_RESONANCE_EFFECTS = [
    "Aetheric Feedback: Target takes minor magical backlash.",
    "Spatial slip: The caster is displaced by 5 feet.",
    "Gravity Warp: Ground becomes difficult terrain for 1 turn.",
    "Temporal echo: Next action delayed by 1 turn.",
    "Chromatic Flare: All nearby entities are temporarily dazzled."
]

def validate_stat(val: float) -> float:
    """Clamps a character attribute to the 2-8 scale."""
    return max(2.0, min(8.0, float(val)))

def calculate_max_health(endurance: float, fortitude: float, vitality: float) -> int:
    """Max Health = Endurance + Fortitude + Vitality"""
    return int(validate_stat(endurance) + validate_stat(fortitude) + validate_stat(vitality))

def calculate_max_composure(willpower: float, logic: float, charm: float) -> int:
    """Max Composure = Willpower + Logic + Charm"""
    return int(validate_stat(willpower) + validate_stat(logic) + validate_stat(charm))

def calculate_max_stamina(might: float, reflex: float, finesse: float) -> int:
    """Max Stamina = Might + Reflexes + Finesse"""
    return int(validate_stat(might) + validate_stat(reflex) + validate_stat(finesse))

def calculate_max_focus(knowledge: float, awareness: float, intuition: float) -> int:
    """Max Focus = Knowledge + Awareness + Intuition"""
    return int(validate_stat(knowledge) + validate_stat(awareness) + validate_stat(intuition))

def get_derived_substats(char_stats: Dict[str, float]) -> Dict[str, int]:
    """
    Synthesizes the core 12 attributes into four derived sub-stats.
    Perception = Awareness + Logic + Vitality
    Stealth & Camo = Knowledge + Charm + Finesse
    Movement & Speed = Reflexes + Might + Intuition
    Balance = Endurance + Fortitude + Willpower
    """
    aw = validate_stat(char_stats.get("awareness", 3.0))
    lo = validate_stat(char_stats.get("logic", 3.0))
    vi = validate_stat(char_stats.get("vitality", 3.0))
    
    kn = validate_stat(char_stats.get("knowledge", 3.0))
    ch = validate_stat(char_stats.get("charm", 3.0))
    fi = validate_stat(char_stats.get("finesse", 3.0))
    
    # Check both reflex and reflexes just in case
    ref = validate_stat(char_stats.get("reflex", char_stats.get("reflexes", 3.0)))
    mi = validate_stat(char_stats.get("might", 3.0))
    in_stat = validate_stat(char_stats.get("intuition", 3.0))
    
    en = validate_stat(char_stats.get("endurance", 3.0))
    fo = validate_stat(char_stats.get("fortitude", 3.0))
    wi = validate_stat(char_stats.get("willpower", 3.0))
    
    return {
        "perception": int(aw + lo + vi),
        "stealth_camo": int(kn + ch + fi),
        "movement_speed": int(ref + mi + in_stat),
        "balance": int(en + fo + wi)
    }

def resolve_brutal_shatter(attacker_tags: List[str], defender_tags: List[str]) -> bool:
    """
    If a kinetic attack carries the #Brutal tag and targets an object or entity with
    the #Brittle tag, automatically shatter the target with zero resource cost,
    completely bypassing standard HP math.
    """
    has_brutal = any(tag.lower() == "#brutal" or tag.lower() == "brutal" for tag in attacker_tags)
    has_brittle = any(tag.lower() == "#brittle" or tag.lower() == "brittle" for tag in defender_tags)
    return has_brutal and has_brittle

def calculate_gear_tax(weapon_tier: int, armor_tier: int, hardware_tier: int) -> int:
    """
    Deductions: Light=-1, Medium=-2, Heavy=-3.
    Hardware Buffer: Tier 2 (+1 buffer), Tier 6 (+2 buffer) offsets gear tax.
    Returns net gear tax (non-positive integer).
    """
    # map absolute values to negative tax deductions if positive numbers are passed
    w_tax = -abs(weapon_tier) if weapon_tier != 0 else 0
    a_tax = -abs(armor_tier) if armor_tier != 0 else 0
    
    total_tax = w_tax + a_tax
    
    # Buffer calculation
    buffer = 0
    if hardware_tier >= 6:
        buffer = 2
    elif hardware_tier >= 2:
        buffer = 1
        
    # Offset the deduction (bring it closer to 0, cannot exceed 0)
    net_tax = min(0, total_tax + buffer)
    return net_tax

def calculate_operational_capacity(max_pool_capacity: int, weapon_tier: int, armor_tier: int, hardware_tier: int) -> Dict[str, Any]:
    """
    Applies gear tax to a resource pool capacity and determines if the 50% threshold throttles regeneration.
    """
    net_tax = calculate_gear_tax(weapon_tier, armor_tier, hardware_tier)
    modified_capacity = max(0, max_pool_capacity + net_tax)
    
    # 50% Threshold Rule: final net tax exceeds 50% of the max capacity pool
    throttle_regeneration = abs(net_tax) > (max_pool_capacity * 0.5)
    regeneration_rate = 1 if throttle_regeneration else 2
    
    return {
        "max_capacity": max_pool_capacity,
        "net_gear_tax": net_tax,
        "modified_capacity": modified_capacity,
        "regeneration_rate": regeneration_rate,
        "throttle_regeneration": throttle_regeneration
    }

def resolve_contested_clash(perception_a: int, perception_b: int, tactic_a: str, tactic_b: str, roll_a: int, roll_b: int) -> Dict[str, Any]:
    """
    Handles contested rolls and tactic clash resolution.
    On an exact d20 tie: immediately deduct 1 Stamina and 1 Focus token from both entities.
    Lower Perception declares tactic first.
    Resolves winner using 6-Tactic matrix.
    """
    t_a = tactic_a.strip().lower()
    t_b = tactic_b.strip().lower()
    
    is_tie = roll_a == roll_b
    stamina_deduction = 1 if is_tie else 0
    focus_deduction = 1 if is_tie else 0
    
    if perception_a < perception_b:
        declare_first = "A"
    elif perception_b < perception_a:
        declare_first = "B"
    else:
        declare_first = "tie"
        
    outcome = CLASH_MATRIX.get((t_a, t_b), "tie")
    
    return {
        "is_tie": is_tie,
        "stamina_deduction": stamina_deduction,
        "focus_deduction": focus_deduction,
        "declare_first": declare_first,
        "outcome": outcome
    }

def channel_the_chaos(personal_chaos_exposure: float, d100_roll: int) -> Dict[str, Any]:
    """
    Reserve Burns: Channeling the Chaos when resource tokens are at 0.
    Roll d100 against personal_chaos_exposure.
    Match or critical success (roll <= exposure): double action effect, increase exposure.
    Failure (roll > exposure): trigger localized Wild Resonance, spike exposure.
    """
    success = float(d100_roll) <= float(personal_chaos_exposure)
    
    if success:
        # success: double effect, increase exposure by +10.0
        new_exposure = min(100.0, personal_chaos_exposure + 10.0)
        return {
            "success": True,
            "new_exposure": new_exposure,
            "exposure_increase": 10.0,
            "wild_resonance": False,
            "effect_multiplier": 2.0
        }
    else:
        # failure: localized wild resonance, spike exposure by +20.0
        new_exposure = min(100.0, personal_chaos_exposure + 20.0)
        return {
            "success": False,
            "new_exposure": new_exposure,
            "exposure_increase": 20.0,
            "wild_resonance": True,
            "effect_multiplier": 1.0
        }

def check_mutation(personal_chaos_exposure: float, current_mutations: List[str], threshold: float = 90.0) -> Optional[str]:
    """
    Mutation Threshold: exposure > threshold forces a permanent mutation.
    Returns the new mutation if triggered, otherwise None.
    """
    if personal_chaos_exposure > threshold:
        available = [m for m in MUTATION_POOL if m not in current_mutations]
        if available:
            return random.choice(available)
    return None


# =====================================================================
# Phase 10 Equipment, Hazard & Magic Resolution Engine Updates
# =====================================================================

def check_null_bypass(blueprint: Dict[str, Any]) -> bool:
    """
    Evaluates the magic_tier key in an entity's paragon_agent_blueprint (or blueprint dict).
    If it evaluates to "Null", the engine MUST automatically skip all Chaos Blowout risk
    calculations, radiation damage, and spatial distortions.
    """
    if not blueprint:
        return False
    return blueprint.get("magic_tier") == "Null"


def parse_tax_value(tier_or_weight: Any) -> int:
    """
    Maps weight class/tier to a negative stamina/focus deduction:
    Light / 1 -> -1
    Medium / 2 -> -2
    Heavy / 3 -> -3
    """
    if isinstance(tier_or_weight, str):
        weight = tier_or_weight.strip().lower()
        if "light" in weight:
            return -1
        elif "medium" in weight:
            return -2
        elif "heavy" in weight:
            return -3
    elif isinstance(tier_or_weight, (int, float)):
        val = int(tier_or_weight)
        if val == 1:
            return -1
        elif val == 2:
            return -2
        elif val == 3:
            return -3
        else:
            return -abs(val)
    return 0


def apply_static_gear_tax(
    max_stamina: int,
    max_focus: int,
    weapon_weight: Any,
    armor_weight: Any,
    weapon_tax_target: str = "focus",
    armor_tax_target: str = "stamina"
) -> Dict[str, Any]:
    """
    Deducts equipped weapon and armor tiers from the character's Maximum Stamina or Focus pools.
    If the total tax on a pool exceeds 50% of the pool's max capacity, throttles the
    regeneration rate from 2 tokens per turn down to 1 token per turn (Systemic Overload).
    """
    w_tax = parse_tax_value(weapon_weight)
    a_tax = parse_tax_value(armor_weight)
    
    stamina_tax = 0
    focus_tax = 0
    
    if weapon_tax_target.lower() == "stamina":
        stamina_tax += w_tax
    else:
        focus_tax += w_tax
        
    if armor_tax_target.lower() == "stamina":
        stamina_tax += a_tax
    else:
        focus_tax += a_tax
        
    modified_stamina = max(0, max_stamina + stamina_tax)
    modified_focus = max(0, max_focus + focus_tax)
    
    # 50% Threshold Rule
    stamina_throttled = abs(stamina_tax) > (max_stamina * 0.5)
    focus_throttled = abs(focus_tax) > (max_focus * 0.5)
    
    stamina_regeneration = 1 if stamina_throttled else 2
    focus_regeneration = 1 if focus_throttled else 2
    
    return {
        "modified_stamina": modified_stamina,
        "modified_focus": modified_focus,
        "stamina_regeneration": stamina_regeneration,
        "focus_regeneration": focus_regeneration,
        "stamina_tax": stamina_tax,
        "focus_tax": focus_tax
    }


def shatter_gear_mid_combat(current_pools: Dict[str, Any], gear_type: str) -> Dict[str, Any]:
    """
    Shatters an entity's gear mid-combat. Marks the item as shattered, but does NOT restore
    the taxed maximum resource pools (physiological shock of loss).
    """
    updated_pools = dict(current_pools)
    shattered_list = updated_pools.setdefault("shattered_gear", [])
    if gear_type not in shattered_list:
        shattered_list.append(gear_type)
    # Tax remains applied (do not restore modified capacities)
    return updated_pools


def process_full_rest(character_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Performs a Full Rest. Restores maximum capacities by recalculating the gear tax,
    clearing any mid-combat shattered gear markers.
    """
    updated_profile = dict(character_profile)
    # Clear mid-combat shattered gear markers
    if "shattered_gear" in updated_profile:
        updated_profile["shattered_gear"] = []
        
    max_stamina = updated_profile.get("max_stamina", 12)
    max_focus = updated_profile.get("max_focus", 10)
    
    weapon_weight = updated_profile.get("equipped_weapon_weight", "")
    armor_weight = updated_profile.get("equipped_armor_weight", "")
    weapon_target = updated_profile.get("weapon_tax_target", "focus")
    armor_target = updated_profile.get("armor_tax_target", "stamina")
    
    tax_results = apply_static_gear_tax(
        max_stamina=max_stamina,
        max_focus=max_focus,
        weapon_weight=weapon_weight,
        armor_weight=armor_weight,
        weapon_tax_target=weapon_target,
        armor_tax_target=armor_target
    )
    
    updated_profile.update({
        "modified_stamina": tax_results["modified_stamina"],
        "modified_focus": tax_results["modified_focus"],
        "stamina_regeneration": tax_results["stamina_regeneration"],
        "focus_regeneration": tax_results["focus_regeneration"],
        "stamina_tax": tax_results["stamina_tax"],
        "focus_tax": tax_results["focus_tax"],
        "current_stamina": tax_results["modified_stamina"],
        "current_focus": tax_results["modified_focus"]
    })
    return updated_profile


def evaluate_chaos_activation(
    blueprint: Dict[str, Any],
    roll_d20: int,
    active_chaos_number: int,
    chaos_ticks: int
) -> Dict[str, Any]:
    """
    Gifted casters (magic_tier != "Null") activating anomalies/magitech trigger the Chaos Engine.
    Roll d20 vs active Chaos Number:
    - Glitch Margin (±1 at 4-6 ticks, ±2 at 7-9 ticks): succeeds, triggers Wild Resonance, +1 Chaos Tick.
    - Miss by 5+: fails, Wild Resonance targets only the user, +2 Chaos Ticks.
    """
    if check_null_bypass(blueprint):
        return {
            "bypass": True,
            "success": True,
            "wild_resonance": None,
            "resonance_target": None,
            "chaos_tracker_add_ticks": 0,
            "msg": "Null Bypass: Chaos calculations skipped."
        }
        
    difference = roll_d20 - active_chaos_number
    
    # Determine Glitch Margin
    margin = 0
    if 4 <= chaos_ticks <= 6:
        margin = 1
    elif 7 <= chaos_ticks <= 9:
        margin = 2
        
    is_glitch = margin > 0 and abs(difference) <= margin
    is_miss_5_plus = difference <= -5
    
    wild_resonance = None
    resonance_target = None
    chaos_tracker_add_ticks = 0
    success = False
    
    if is_glitch:
        success = True
        wild_resonance = random.choice(WILD_RESONANCE_EFFECTS)
        resonance_target = "all"
        chaos_tracker_add_ticks = 1
        msg = f"Glitch Margin triggered: Action succeeds with Wild Resonance: '{wild_resonance}' (+1 Chaos Tick)."
    elif is_miss_5_plus:
        success = False
        wild_resonance = random.choice(WILD_RESONANCE_EFFECTS)
        resonance_target = "user_only"
        chaos_tracker_add_ticks = 2
        msg = f"Critical Miss by 5+: Action fails. Wild Resonance targets user: '{wild_resonance}' (+2 Chaos Ticks)."
    else:
        if roll_d20 >= active_chaos_number:
            success = True
            msg = "Action succeeded normally."
        else:
            success = False
            msg = "Action failed normally."
            
    return {
        "bypass": False,
        "success": success,
        "wild_resonance": wild_resonance,
        "resonance_target": resonance_target,
        "chaos_tracker_add_ticks": chaos_tracker_add_ticks,
        "msg": msg
    }


def resolve_magic_duel(
    caster_a_blueprint: Dict[str, Any],
    caster_b_blueprint: Dict[str, Any],
    current_chaos_ticks: int
) -> Dict[str, Any]:
    """
    Magic Duel Absolute Rule: If both casters are Gifted (neither magic_tier is "Null"),
    automatically add +1 Tick to the Chaos Tracker regardless of the roll result.
    """
    is_duel = (
        caster_a_blueprint.get("magic_tier") != "Null" and
        caster_b_blueprint.get("magic_tier") != "Null"
    )
    
    add_ticks = 1 if is_duel else 0
    new_ticks = current_chaos_ticks + add_ticks
    
    return {
        "is_magic_duel": is_duel,
        "added_ticks": add_ticks,
        "new_chaos_ticks": new_ticks,
        "msg": "Magic Duel: +1 Chaos Tick added automatically." if is_duel else "Not a Magic Duel between two Gifted casters."
    }
