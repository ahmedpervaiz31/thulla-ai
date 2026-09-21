"""Shared budgets, thresholds, and dump-tier tables for bot MC / heuristics."""

KEEPER_RANKS = frozenset({"2", "3", "4", "5"})
MID_RANKS = frozenset({"6", "7", "8", "9", "10"})
FACE_DUMP_VALUES = {"A": 10, "K": 9, "Q": 8, "J": 7}
MID_DUMP_VALUES = {"10": 5, "9": 4, "8": 3, "7": 2, "6": 1}
KEEPER_DUMP_VALUES = {"5": -1, "4": -2, "3": -3, "2": -4}
LONG_SUIT_LEN = 4
HEAVY_DISCARD_COUNT = 6
DUMP_SAFE_P_THRESHOLD = 0.5
# Soft floor when a later seat ducked with a keeper (2–5) under a higher card.
# Above DUMP_SAFE_P_THRESHOLD so the suit fails lead dump-safe.
KEEPER_DUCK_VOID_FLOOR = 0.65
TAKE_UNKNOWN_MAX = 20
TAKE_MARGIN = 0.1
TAKE_MARGIN_SAFE_FACE = 0.15
LEAD_PICKUP_WEIGHT = 0.2
LEAD_LIABILITY_WEIGHT = 0.1
LEAD_TIER_WEIGHT = 0.08
LEAD_SUIT_VOID_WEIGHT = 0.3
LEAD_VOID_COUNT_WEIGHT = 0.15
LOOKAHEAD_SAMPLES = 48
THULLA_ESCAPE_WEIGHT = 0.2
THULLA_SHED_WEIGHT = 0.15
THULLA_ESCAPE_HORIZON = 3
# Sticky away/shed only when escape looks live; else dump liabilities.
THULLA_ESCAPE_LIVE = 0.3
THULLA_LIABILITY_WEIGHT = 0.25
# Full-game lose rollouts are expensive; only when the unknown pool is small.
THULLA_FULL_LOSE_MAX_UNKNOWN = 20
THULLA_LOSE_MAX_TRICKS = 48
THULLA_MC_MAX_CANDIDATES = 4
