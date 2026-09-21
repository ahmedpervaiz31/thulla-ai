"""Take / merge helpers (soft case-A hint + MC lose-rate compare)."""

from __future__ import annotations

from .rollouts import _build_full_hands, _n_player_i_lose
from .sampling import _sample_deals

_SUITS = ("Diamond", "Heart", "Spade", "Club")
# Neighbor larger than this: merge is usually desperation, not a clean borrow.
_FEEDER_MAX_CARDS = 5


def case_a_should_take(view, my_hand, neighbor_idx):
    """Conservative merge signal — one void + a big hand is not enough.

    Soft hint for Ideal Move only — does not force CPU takes by itself.
    """
    n = view.hand_size(neighbor_idx)
    if n >= 5:
        return False

    my_suits = {c.colour for c in my_hand}
    useful_voids = [s for s in _SUITS if view.is_void(neighbor_idx, s) and s in my_suits]

    if len(useful_voids) >= 2:
        return True

    if n > 3:
        return False

    if useful_voids:
        return True

    known = list(view.visible_cards(neighbor_idx, my_hand))
    if not known:
        return False
    my_voids = set()
    for s in _SUITS:
        if view.is_void(view.me, s) or not any(c.colour == s for c in my_hand):
            my_voids.add(s)
    hits = sum(1 for c in known if c.colour in my_voids)
    return hits * 2 >= len(known)


def mono_suit_feeder_should_take(view, my_hand, neighbor_idx):
    """Ask when continuing to play into this neighbor leaks cards publicly.

    Pattern (48fd9511): neighbor is down to one followable suit, someone later is
    void in that suit, and we already hold that suit (usually from their thulla
    dumps). Then:
      - lead their suit → they undercut → later seat thullas us (public pickup)
      - lead into their voids → they dump onto us (more public pickup)
    Taking merges privately: same cards, no table info for the others.

    Kept narrow on purpose — not an eager "take any small hand" rule.
    """
    n = view.hand_size(neighbor_idx)
    if n <= 0 or n > _FEEDER_MAX_CARDS:
        return False

    voids = [s for s in _SUITS if view.is_void(neighbor_idx, s)]
    if len(voids) < 2:
        return False
    remain = [s for s in _SUITS if s not in voids]
    if len(remain) != 1:
        return False
    suit = remain[0]

    others = [
        p for p in view.active_indices if p != view.me and p != neighbor_idx
    ]
    if not any(view.is_void(p, suit) for p in others):
        return False

    # Already in their suit ⇒ we're in the undercut / thulla loop with them.
    if not any(c.colour == suit for c in my_hand):
        return False
    return True


def compare_take_lose_rates(view, my_hand, neighbor_idx, samples=40):
    """Return (lose_rate_keep, lose_rate_merge) via N-player survival rollouts."""
    active = list(view.active_indices)
    me = view.me
    if neighbor_idx not in active or me not in active or len(active) < 3:
        return 1.0, 1.0

    lose_keep = 0
    lose_merge = 0
    n = 0
    for dealt in _sample_deals(view, my_hand, samples):
        n += 1
        full = _build_full_hands(view, my_hand, dealt)

        keep_hands = [list(full[p]) for p in active]
        me_keep = active.index(me)
        if _n_player_i_lose(keep_hands, me_keep, me_keep, use_survival=True):
            lose_keep += 1

        merged_seats = [p for p in active if p != neighbor_idx]
        merge_hands = []
        for p in merged_seats:
            if p == me:
                merge_hands.append(list(my_hand) + list(full[neighbor_idx]))
            else:
                merge_hands.append(list(full[p]))
        me_merge = merged_seats.index(me)
        if _n_player_i_lose(merge_hands, me_merge, me_merge, use_survival=True):
            lose_merge += 1

    if n == 0:
        return 1.0, 1.0
    return lose_keep / n, lose_merge / n
