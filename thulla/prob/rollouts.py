"""Survival / trick-1 playout helpers used by take, lead, and thulla MC."""

from __future__ import annotations

from ..cards import raise_equivalence
from .constants import LONG_SUIT_LEN
from .dump import dump_tier, dump_value, is_face, is_keeper


def _pad_hand(cards, size):
    return list(cards)[:size] if len(cards) >= size else list(cards)


def _build_full_hands(view, my_hand, dealt):
    """Expand a partial deal sample into padded seat hands."""
    active = list(view.active_indices)
    me = view.me
    others = [p for p in active if p != me]
    full = [[] for _ in range(view.player_cnt)]
    full[me] = list(my_hand)
    for p in others:
        known = list(view.visible_cards(p, my_hand))
        sampled = list(dealt.get(p, []))
        full[p] = _pad_hand(known + sampled, view.hand_size(p))
    return full


def _survival_lead_card(hand):
    """Lead heuristic for rollouts: highest dump tier, prefer shorter suits."""
    by_suit = {}
    for c in hand:
        by_suit.setdefault(c.colour, []).append(c)

    def best_in_suit(s):
        return max(by_suit[s], key=lambda c: (dump_tier(c), dump_value(c), c))

    def suit_score(s):
        best = best_in_suit(s)
        return (-dump_tier(best), len(by_suit[s]), -dump_value(best))

    # Prefer suits that are not obviously long when dumping faces/mids.
    ranked = sorted(by_suit.keys(), key=suit_score)
    for suit in ranked:
        best = best_in_suit(suit)
        if dump_tier(best) >= 2 and len(by_suit[suit]) >= LONG_SUIT_LEN:
            continue
        if dump_tier(best) >= 1:
            return raise_equivalence(best, hand, hand, accounted=set(hand))

    suit = min(by_suit, key=lambda s: (len(by_suit[s]), min(by_suit[s])))
    non_keepers = [c for c in by_suit[suit] if not is_keeper(c)]
    choice = min(non_keepers) if non_keepers else min(by_suit[suit])
    return raise_equivalence(choice, hand, hand, accounted=set(hand))


def _survival_respond(hand, lead_card, highest):
    """Follow/thulla heuristic: cash faces on follow without length gate."""
    same = [c for c in hand if c.colour == lead_card.colour]
    if same:
        winners = [c for c in same if highest is None or c > highest]
        under = [c for c in same if highest is not None and c < highest]
        face_winners = [c for c in winners if is_face(c)]
        # Rollouts have no void view — cash face winners; otherwise best dump.
        if face_winners:
            choice = max(face_winners, key=lambda c: (dump_value(c), c))
        elif winners and not under:
            choice = max(winners, key=lambda c: (dump_tier(c), dump_value(c), c))
        elif under:
            choice = max(under, key=lambda c: (dump_tier(c), dump_value(c), c))
        elif winners:
            choice = min(winners)
        else:
            choice = max(same, key=lambda c: (dump_tier(c), dump_value(c), c))
        return raise_equivalence(choice, hand, same, accounted=set(hand))
    faces = [c for c in hand if is_face(c)]
    if faces:
        choice = max(faces, key=lambda c: (dump_value(c), c))
    else:
        non_keepers = [c for c in hand if not is_keeper(c)]
        pool = non_keepers if non_keepers else hand
        choice = max(pool, key=lambda c: (dump_tier(c), dump_value(c), c))
    return raise_equivalence(choice, hand, hand, accounted=set(hand))


def _respond(hand, lead):
    """Legacy duck-follow used by take sims."""
    same = [c for c in hand if c.colour == lead.colour]
    if same:
        under = [c for c in same if c < lead]
        choice = max(under) if under else min(same)
        return raise_equivalence(choice, hand, same, accounted=set(hand))
    return raise_equivalence(max(hand), hand, hand, accounted=set(hand))


def _n_player_i_lose(hands, me_idx, leader_idx, max_tricks=200, use_survival=True):
    """Full-game sim. True iff me_idx is the sole leftover (last)."""
    hands = [list(h) for h in hands]
    n = len(hands)
    leader = leader_idx
    for _ in range(max_tricks):
        active = [i for i in range(n) if hands[i]]
        if len(active) <= 1:
            return bool(active) and active[0] == me_idx
        if leader not in active:
            leader = active[0]
        order = []
        start = active.index(leader)
        for k in range(len(active)):
            order.append(active[(start + k) % len(active)])
        stack = []
        colour = None
        highest = None
        highest_p = leader
        thulla = False
        for j, p in enumerate(order):
            if j == 0:
                if use_survival:
                    card = _survival_lead_card(hands[p])
                else:
                    card = min(hands[p])
                colour = card.colour
                highest = card
                highest_p = p
            else:
                if use_survival:
                    card = _survival_respond(hands[p], stack[0], highest)
                else:
                    card = _respond(hands[p], stack[0])
            hands[p].remove(card)
            stack.append(card)
            if card.colour != colour:
                hands[highest_p].extend(stack)
                leader = highest_p
                thulla = True
                break
            if card > highest:
                highest = card
                highest_p = p
        if not thulla:
            leader = highest_p
    survivors = [i for i in range(n) if hands[i]]
    return len(survivors) == 1 and survivors[0] == me_idx


def _trick1_play_card(hand, lead_card, highest, player_idx, view=None):
    """Play one card on trick 1; force thulla when player is a known void in led suit."""
    suit = lead_card.colour
    same = [c for c in hand if c.colour == suit]
    if view is not None and view.is_void(player_idx, suit):
        same = []
    if same:
        winners = [c for c in same if highest is None or c > highest]
        under = [c for c in same if highest is not None and c < highest]
        face_winners = [c for c in winners if is_face(c)]
        if face_winners:
            choice = max(face_winners, key=lambda c: (dump_value(c), c))
        elif winners and not under:
            choice = max(winners, key=lambda c: (dump_tier(c), dump_value(c), c))
        elif under:
            choice = max(under, key=lambda c: (dump_tier(c), dump_value(c), c))
        elif winners:
            choice = min(winners)
        else:
            choice = max(same, key=lambda c: (dump_tier(c), dump_value(c), c))
        return raise_equivalence(choice, hand, same, accounted=set(hand))
    faces = [c for c in hand if is_face(c)]
    if faces:
        choice = max(faces, key=lambda c: (dump_value(c), c))
    else:
        non_keepers = [c for c in hand if not is_keeper(c)]
        pool = non_keepers if non_keepers else hand
        choice = max(pool, key=lambda c: (dump_tier(c), dump_value(c), c))
    return raise_equivalence(choice, hand, hand, accounted=set(hand))


def _trick1_order(me_idx, active_seats, hands):
    n = len(hands)
    active_set = set(active_seats)
    order = []
    for k in range(1, n + 1):
        j = (me_idx + k) % n
        if j in active_set and hands[j]:
            order.append(j)
    return order


def _trick1_self_pickup(hands, me_idx, lead_card, active_seats, view=None):
    """True iff leader picks up the pot on trick 1 via thulla."""
    order = _trick1_order(me_idx, active_seats, hands)
    stack = [lead_card]
    colour = lead_card.colour
    highest = lead_card
    highest_p = me_idx
    thulla = False
    for p in order:
        card = _trick1_play_card(hands[p], lead_card, highest, p, view=view)
        hands[p].remove(card)
        stack.append(card)
        if card.colour != colour:
            hands[highest_p].extend(stack)
            thulla = True
            break
        if card > highest:
            highest = card
            highest_p = p
    return thulla and highest_p == me_idx


def _lead_card_then_lose(hands, me_idx, lead_card, active_seats, view=None):
    """Play one trick with me leading lead_card, then survival playout. Return if me last."""
    order = _trick1_order(me_idx, active_seats, hands)
    stack = [lead_card]
    colour = lead_card.colour
    highest = lead_card
    highest_p = me_idx
    thulla = False
    for p in order:
        card = _trick1_play_card(hands[p], lead_card, highest, p, view=view)
        hands[p].remove(card)
        stack.append(card)
        if card.colour != colour:
            hands[highest_p].extend(stack)
            thulla = True
            leader = highest_p
            break
        if card > highest:
            highest = card
            highest_p = p
    if not thulla:
        leader = highest_p
    return _n_player_i_lose(hands, me_idx, leader, use_survival=True)


def _survival_trick_once(hands, leader_idx):
    """Play one survival-policy trick.

    Returns (next_leader, discarded_set_or_None, thulla).
    discarded_set is the clean-trick stack when not thulla; else None.
    """
    active = [i for i in range(len(hands)) if hands[i]]
    if len(active) <= 1:
        return leader_idx, None, False
    if leader_idx not in active:
        leader_idx = active[0]
    order = []
    start = active.index(leader_idx)
    for k in range(len(active)):
        order.append(active[(start + k) % len(active)])
    stack = []
    colour = None
    highest = None
    highest_p = leader_idx
    for j, p in enumerate(order):
        if j == 0:
            card = _survival_lead_card(hands[p])
            colour = card.colour
            highest = card
            highest_p = p
        else:
            card = _survival_respond(hands[p], stack[0], highest)
        hands[p].remove(card)
        stack.append(card)
        if card.colour != colour:
            hands[highest_p].extend(stack)
            return highest_p, None, True
        if card > highest:
            highest = card
            highest_p = p
    return highest_p, set(stack), False
