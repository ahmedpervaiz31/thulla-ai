"""Dump tiers and lead/follow safety heuristics."""

from __future__ import annotations

from .constants import (
    DUMP_SAFE_P_THRESHOLD,
    FACE_DUMP_VALUES,
    HEAVY_DISCARD_COUNT,
    KEEPER_DUMP_VALUES,
    KEEPER_RANKS,
    LONG_SUIT_LEN,
    MID_DUMP_VALUES,
    MID_RANKS,
)
from .sampling import estimate_thulla_prob


def is_keeper(card):
    return card.number in KEEPER_RANKS


def is_mid(card):
    return card.number in MID_RANKS


def is_face(card):
    return card.number in FACE_DUMP_VALUES


def dump_tier(card):
    """2 = face, 1 = mid (6–10), 0 = keeper (2–5)."""
    if card.number in FACE_DUMP_VALUES:
        return 2
    if card.number in MID_RANKS:
        return 1
    return 0


def dump_value(card):
    """Higher = prefer dumping. Faces > mids > keepers."""
    if card.number in FACE_DUMP_VALUES:
        return FACE_DUMP_VALUES[card.number]
    if card.number in MID_DUMP_VALUES:
        return MID_DUMP_VALUES[card.number]
    if card.number in KEEPER_DUMP_VALUES:
        return KEEPER_DUMP_VALUES[card.number]
    return 0


def suit_length(hand, suit):
    return sum(1 for c in hand if c.colour == suit)


def discarded_of_suit(view, suit):
    return sum(1 for c in view._info.discarded if c.colour == suit)


def suit_dump_safe(view, hand, suit, seats_after, p_thulla=None, threshold=DUMP_SAFE_P_THRESHOLD):
    """True when *leading* a face in `suit` is acceptable (shape + void risk)."""
    seats = list(seats_after or [])
    if any(view.is_void(p, suit) for p in seats):
        return False
    if p_thulla is None:
        p_thulla = estimate_thulla_prob(view, suit, hand, seats_after=seats)
    if p_thulla >= threshold:
        return False
    length = suit_length(hand, suit)
    if length >= LONG_SUIT_LEN:
        return False
    if discarded_of_suit(view, suit) >= HEAVY_DISCARD_COUNT and length >= 3:
        return False
    return True


def follow_take_safe(view, hand, suit, seats_after, p_thulla=None, threshold=DUMP_SAFE_P_THRESHOLD):
    """True when *winning* the trick on follow is acceptable (void risk only).

    Length / heavy-discard are lead-shape concerns and must not block cashing A/K/Q/J.
    """
    seats = list(seats_after or [])
    if any(view.is_void(p, suit) for p in seats):
        return False
    if p_thulla is None:
        p_thulla = estimate_thulla_prob(view, suit, hand, seats_after=seats)
    return p_thulla < threshold


def has_dump_safe_face_lead(view, hand, seats_after=None, samples=200):
    """True if we can still lead a face in a dump-safe suit (survive another round)."""
    seats = list(seats_after) if seats_after is not None else [
        p for p in view.active_indices if p != view.me
    ]
    by_suit = {}
    for c in hand:
        by_suit.setdefault(c.colour, []).append(c)
    for suit, cards in by_suit.items():
        if not any(is_face(c) for c in cards):
            continue
        if any(view.is_void(p, suit) for p in seats):
            continue
        p = estimate_thulla_prob(view, suit, hand, seats_after=seats, samples=samples)
        if suit_dump_safe(view, hand, suit, seats, p_thulla=p):
            return True
    return False
