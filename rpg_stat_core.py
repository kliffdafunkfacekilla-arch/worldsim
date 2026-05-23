import random
from typing import Dict, List, Any, Optional

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

def check_mutation(personal_chaos_exposure: float, current_mutations: List[str]) -> Optional[str]:
    """
    Mutation Threshold: exposure > 90.0 forces a permanent mutation.
    Returns the new mutation if triggered, otherwise None.
    """
    if personal_chaos_exposure > 90.0:
        available = [m for m in MUTATION_POOL if m not in current_mutations]
        if available:
            return random.choice(available)
    return None
