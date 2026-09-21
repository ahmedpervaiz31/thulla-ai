"""Deal sampling under hard PublicInfo constraints (+ void P estimates)."""

from __future__ import annotations

import random

from .constants import KEEPER_DUCK_VOID_FLOOR, KEEPER_RANKS


def keeper_duck_near_void(view, seat, suit) -> bool:
    """True if seat ducked with a keeper (2–5) under a higher card in suit.

    Soft convention only — not a hard void (sandbagging is legal).
    """
    under = view.under_ceiling(seat, suit)
    if under is None:
        return False
    played, _ceiling = under
    return played.number in KEEPER_RANKS


def any_keeper_duck_after(view, seats, suit) -> bool:
    return any(keeper_duck_near_void(view, p, suit) for p in seats)


def estimate_thulla_prob(view, suit, my_hand, seats_after, samples=200):
    """P(someone in seats_after cannot follow suit).

    Soft floor when a later seat has a keeper-duck under-ceiling (human prior:
    dumping 2–5 under a high card usually means near-empty in that suit).
    """
    seats = list(seats_after)
    if not seats:
        return 0.0
    if any(view.is_void(p, suit) for p in seats):
        return 1.0

    max_copies = len(view.unseen_of(suit, my_hand))
    for p in seats:
        max_copies += sum(1 for c in view.visible_cards(p, my_hand) if c.colour == suit)
    if len(seats) > max_copies:
        return 1.0

    if all(any(c.colour == suit for c in view.visible_cards(p, my_hand)) for p in seats):
        if not any(c.colour == suit for c in view.free_cards(my_hand)):
            p = 0.0
            if any_keeper_duck_after(view, seats, suit):
                return max(p, KEEPER_DUCK_VOID_FLOOR)
            return p

    hits = 0
    for dealt in _sample_deals(view, my_hand, samples):
        if _someone_void(dealt, view, seats, suit, my_hand):
            hits += 1
    p = hits / max(1, samples)
    if any_keeper_duck_after(view, seats, suit):
        p = max(p, KEEPER_DUCK_VOID_FLOOR)
    return p


def _someone_void(dealt, view, seats, suit, my_hand):
    for p in seats:
        if view.is_void(p, suit):
            return True
        has = any(c.colour == suit for c in view.visible_cards(p, my_hand))
        has = has or any(c.colour == suit for c in dealt.get(p, []))
        if not has:
            return True
    return False


def _sample_deals(view, my_hand, samples):
    others = [p for p in view.active_indices if p != view.me]
    slots = {p: view.unknown_slots(p, my_hand) for p in others}
    total_slots = sum(slots.values())
    free = list(view.free_cards(my_hand))
    void_masks = {p: set(view._info.voids.get(p, set())) for p in others}
    # Hard bans only (suit voids via cannot_hold). Soft duck / suit-high
    # hints must not erase cards from the deal pool — sandbagging is legal.
    banned = {
        p: {c for c in free if view.cannot_hold(p, c)} for p in others
    }

    if total_slots <= 0:
        empty = {p: [] for p in others}
        for _ in range(samples):
            yield empty
        return

    for _ in range(samples):
        if len(free) > total_slots:
            pool = random.sample(free, total_slots)
        else:
            pool = list(free)
        yield _deal_once(others, slots, pool, void_masks, banned)


def _deal_once(others, slots, pool, void_masks, banned=None):
    banned = banned or {}
    random.shuffle(pool)
    dealt = {p: [] for p in others}
    remaining = list(pool)

    # First pass: only legal (non-void / non-banned) assignments
    still = []
    for card in remaining:
        placed = False
        candidates = [
            p
            for p in others
            if len(dealt[p]) < slots[p]
            and card.colour not in void_masks[p]
            and card not in banned.get(p, ())
        ]
        if candidates:
            # Fill players with most remaining need first for stability
            candidates.sort(key=lambda p: slots[p] - len(dealt[p]), reverse=True)
            dealt[candidates[0]].append(card)
            placed = True
        if not placed:
            still.append(card)

    # Second pass: force-fill if constraints were over-tight
    for card in still:
        for p in others:
            if len(dealt[p]) < slots[p]:
                dealt[p].append(card)
                break
    return dealt


def count_free_unknown(view, my_hand):
    return len(view.free_cards(my_hand))
