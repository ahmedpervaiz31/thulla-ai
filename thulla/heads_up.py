"""Exact perfect-info search for heads-up (1v1) Thulla."""

from __future__ import annotations

import time

from .cards import cards_of_suit, raise_equivalence, valid_moves
from .prob import dump_tier, dump_value

MAX_NODES = 80_000
# Combined cards above this: fall back to MC (branching explodes).
MAX_EXACT_CARDS = 14
# UI/bot wall-clock cap so Ideal Move never waits out a full node miss.
DEFAULT_MAX_MS = 350

# Lexicographic value: (outcome, margin)
# outcome +1 win / -1 lose; on loss margin = -len(me) so fewer cards left is better.
_WIN = (1, 0)
_BUDGET_FAIL = (-1, -999)
_ME_MIN = (-2, 0)  # sentinel below any real value when maximizing
_ME_MAX = (2, 0)  # sentinel above any real value when minimizing


class _Budget:
    __slots__ = ("nodes", "max_nodes", "exhausted", "deadline")

    def __init__(self, max_nodes=MAX_NODES, max_ms=None):
        self.nodes = 0
        self.max_nodes = max_nodes
        self.exhausted = False
        self.deadline = None if max_ms is None else (time.perf_counter() + max_ms / 1000.0)

    def hit(self):
        self.nodes += 1
        if self.nodes > self.max_nodes:
            self.exhausted = True
            return True
        if self.deadline is not None and time.perf_counter() >= self.deadline:
            self.exhausted = True
            return True
        return False


def exact_best_move(
    my_hand,
    opp_hand,
    *,
    i_am_leader,
    lead_card=None,
    highest=None,
    max_nodes=MAX_NODES,
    max_ms=None,
):
    """Best card for me under optimal 1v1 play.

    Returns None if search budget is exhausted (caller should fall back).
    """
    card, _value = exact_best_move_with_value(
        my_hand,
        opp_hand,
        i_am_leader=i_am_leader,
        lead_card=lead_card,
        highest=highest,
        max_nodes=max_nodes,
        max_ms=max_ms,
    )
    return card


def exact_best_move_with_value(
    my_hand,
    opp_hand,
    *,
    i_am_leader,
    lead_card=None,
    highest=None,
    max_nodes=MAX_NODES,
    max_ms=None,
):
    """Best card and (outcome, margin), or (None, None) if budget exhausted."""
    me = list(my_hand)
    opp = list(opp_hand)
    if not me:
        return None, None
    budget = _Budget(max_nodes=max_nodes, max_ms=max_ms)
    memo = {}
    accounted = set(me) | set(opp)

    if lead_card is None:
        if not i_am_leader:
            return None, None
        moves = valid_moves(me, None)
        candidates = _order_leads(me, moves, accounted, opp)
        best_card = None
        best_value = None
        best_key = None
        for card in candidates:
            if budget.hit():
                return None, None
            me2 = _without(me, card)
            # Fresh window per root move so values stay exact for tie-breaks.
            v = _value_after_response(
                me2,
                opp,
                lead=card,
                high=card,
                high_is_me=True,
                responder_is_me=False,
                memo=memo,
                budget=budget,
                alpha=_ME_MIN,
                beta=_ME_MAX,
            )
            if budget.exhausted:
                return None, None
            key = _move_key(v, card, opp)
            if best_key is None or key > best_key:
                best_key = key
                best_card = card
                best_value = v
        return best_card, best_value

    # Responding (follow or thulla)
    high = highest if highest is not None else lead_card
    high_is_me = False
    moves = valid_moves(me, cards_of_suit(lead_card.colour))
    candidates = _order_responses(me, moves, accounted, lead_card, high)
    best_card = None
    best_value = None
    best_key = None
    for card in candidates:
        if budget.hit():
            return None, None
        me2 = _without(me, card)
        high2 = high
        high_is_me2 = high_is_me
        if card.colour == lead_card.colour and card > high2:
            high2 = card
            high_is_me2 = True
        v = _resolve_and_value(
            me2,
            opp,
            lead=lead_card,
            high=high2,
            high_is_me=high_is_me2,
            resp=card,
            resp_is_me=True,
            memo=memo,
            budget=budget,
            alpha=_ME_MIN,
            beta=_ME_MAX,
        )
        if budget.exhausted:
            return None, None
        key = _move_key(v, card, opp, lead_suit=lead_card.colour)
        if best_key is None or key > best_key:
            best_key = key
            best_card = card
            best_value = v
    return best_card, best_value


def exact_move_outcome(
    my_hand,
    opp_hand,
    card,
    *,
    i_am_leader,
    lead_card=None,
    highest=None,
    max_nodes=MAX_NODES,
    max_ms=None,
):
    """Return +1 / -1 for playing `card`, or None if budget exhausted."""
    full = exact_move_value(
        my_hand,
        opp_hand,
        card,
        i_am_leader=i_am_leader,
        lead_card=lead_card,
        highest=highest,
        max_nodes=max_nodes,
        max_ms=max_ms,
    )
    if full is None:
        return None
    return full[0]


def exact_move_value(
    my_hand,
    opp_hand,
    card,
    *,
    i_am_leader,
    lead_card=None,
    highest=None,
    max_nodes=MAX_NODES,
    max_ms=None,
):
    """Return (outcome, margin) for playing `card`, or None if budget exhausted."""
    me = list(my_hand)
    opp = list(opp_hand)
    budget = _Budget(max_nodes=max_nodes, max_ms=max_ms)
    memo = {}
    alpha, beta = _ME_MIN, _ME_MAX
    if budget.hit():
        return None
    if lead_card is None:
        if not i_am_leader or card not in me:
            return None
        me2 = _without(me, card)
        v = _value_after_response(
            me2,
            opp,
            lead=card,
            high=card,
            high_is_me=True,
            responder_is_me=False,
            memo=memo,
            budget=budget,
            alpha=alpha,
            beta=beta,
        )
        return None if budget.exhausted else v

    if card not in me:
        return None
    high = highest if highest is not None else lead_card
    me2 = _without(me, card)
    high2 = high
    high_is_me2 = False
    if card.colour == lead_card.colour and card > high2:
        high2 = card
        high_is_me2 = True
    v = _resolve_and_value(
        me2,
        opp,
        lead=lead_card,
        high=high2,
        high_is_me=high_is_me2,
        resp=card,
        resp_is_me=True,
        memo=memo,
        budget=budget,
        alpha=alpha,
        beta=beta,
    )
    return None if budget.exhausted else v


def try_exact_from_view(
    hand, moves, expected_cards, view, *, max_nodes=MAX_NODES, max_ms=DEFAULT_MAX_MS
):
    """If heads-up complete info, return exact best card in `moves`; else None."""
    card, _value = try_exact_with_value_from_view(
        hand, moves, expected_cards, view, max_nodes=max_nodes, max_ms=max_ms
    )
    return card


def try_exact_with_value_from_view(
    hand, moves, expected_cards, view, *, max_nodes=MAX_NODES, max_ms=DEFAULT_MAX_MS
):
    """Like try_exact_from_view, but also return (outcome, margin) from the same search."""
    if view is None or not moves:
        return None, None
    opp = view.heads_up_opponent()
    if opp is None:
        return None, None
    deduced = view.deduced_hand(opp, hand)
    if deduced is None:
        return None, None
    if len(hand) + len(deduced) > MAX_EXACT_CARDS:
        return None, None

    if expected_cards is None:
        card, value = exact_best_move_with_value(
            hand,
            deduced,
            i_am_leader=True,
            lead_card=None,
            max_nodes=max_nodes,
            max_ms=max_ms,
        )
        lead_card = None
        highest = None
        i_am_leader = True
    else:
        lead = expected_cards[0]
        highest = view.current_highest
        card, value = exact_best_move_with_value(
            hand,
            deduced,
            i_am_leader=False,
            lead_card=lead,
            highest=highest,
            max_nodes=max_nodes,
            max_ms=max_ms,
        )
        lead_card = lead
        i_am_leader = False
    if card is None:
        return None, None
    if card not in moves:
        matched = None
        for m in moves:
            if m == card:
                matched = m
                break
        if matched is None:
            return None, None
        card = matched
    return card, value


def exact_principal_line(
    my_hand,
    opp_hand,
    *,
    i_am_leader,
    lead_card=None,
    highest=None,
    first_card=None,
    max_plies=40,
    max_nodes=MAX_NODES,
    max_ms=None,
):
    """Optimal play line from this seat's view (both sides optimal).

    Returns a list of dicts:
      {side: "you"|"opp", card: "2C", note: "lead"|"follow"|"thulla …"|"empty"}
    `first_card` forces the opening move (the Ideal recommendation).
    """
    me = list(my_hand)
    opp = list(opp_hand)
    line = []
    pending_first = first_card

    def search(actor_hand, other_hand, **kwargs):
        return exact_best_move(
            actor_hand,
            other_hand,
            max_nodes=max_nodes,
            max_ms=max_ms,
            **kwargs,
        )

    # Mid-trick: we are responding to lead_card.
    if lead_card is not None:
        if not me:
            return line
        card = pending_first
        pending_first = None
        if card is None or card not in me:
            card = search(
                me,
                opp,
                i_am_leader=False,
                lead_card=lead_card,
                highest=highest,
            )
        if card is None or card not in me:
            return line
        high = highest if highest is not None else lead_card
        high_is_me = False
        if card.colour == lead_card.colour and card > high:
            high = card
            high_is_me = True
        note = _response_note(lead_card, card, high_is_me)
        line.append({"side": "you", "card": card.code(), "note": note})
        me, opp, leader_is_me, end_note = _apply_trick(
            me, opp, lead_card, True, card, True, high_is_me
        )
        if end_note:
            line[-1]["note"] = f"{note}; {end_note}"
        term = _terminal(me, opp)
        if term is not None:
            line.append(
                {
                    "side": "you" if term[0] == 1 else "opp",
                    "card": "",
                    "note": "you empty — win" if term[0] == 1 else "opp empty — you lose",
                }
            )
            return line
        i_am_leader = leader_is_me
        lead_card = None
        highest = None

    plies = 0
    while plies < max_plies:
        plies += 1
        term = _terminal(me, opp)
        if term is not None:
            line.append(
                {
                    "side": "you" if term[0] == 1 else "opp",
                    "card": "",
                    "note": "you empty — win" if term[0] == 1 else "opp empty — you lose",
                }
            )
            break
        if not me or not opp:
            break

        if i_am_leader:
            card = pending_first
            pending_first = None
            if card is None or card not in me:
                card = search(me, opp, i_am_leader=True, lead_card=None)
            if card is None or card not in me:
                break
            line.append({"side": "you", "card": card.code(), "note": "lead"})
            me2 = _without(me, card)
            # Opp responds optimally from their seat.
            if not opp:
                break
            resp = search(
                opp,
                me2,
                i_am_leader=False,
                lead_card=card,
                highest=card,
            )
            if resp is None or resp not in opp:
                break
            high = card
            high_is_me = True
            if resp.colour == card.colour and resp > high:
                high = resp
                high_is_me = False
            if resp.colour != card.colour:
                rnote = "thulla"
            elif high_is_me:
                rnote = "under"
            else:
                rnote = "over"
            line.append({"side": "opp", "card": resp.code(), "note": rnote})
            me, opp, leader_is_me, end_note = _apply_trick(
                me2, opp, card, True, resp, False, high_is_me
            )
            if end_note:
                line[-1]["note"] = f"{rnote}; {end_note}"
            i_am_leader = leader_is_me
        else:
            # Opp leads.
            if not opp:
                break
            lead = search(opp, me, i_am_leader=True, lead_card=None)
            if lead is None or lead not in opp:
                break
            line.append({"side": "opp", "card": lead.code(), "note": "lead"})
            opp2 = _without(opp, lead)
            card = pending_first
            pending_first = None
            if card is None or card not in me:
                card = search(
                    me,
                    opp2,
                    i_am_leader=False,
                    lead_card=lead,
                    highest=lead,
                )
            if card is None or card not in me:
                break
            high = lead
            high_is_me = False
            if card.colour == lead.colour and card > high:
                high = card
                high_is_me = True
            note = _response_note(lead, card, high_is_me)
            line.append({"side": "you", "card": card.code(), "note": note})
            me, opp, leader_is_me, end_note = _apply_trick(
                me, opp2, lead, False, card, True, high_is_me
            )
            if end_note:
                line[-1]["note"] = f"{note}; {end_note}"
            i_am_leader = leader_is_me

    return line


def _response_note(lead, resp, took_high):
    if resp.colour != lead.colour:
        return "thulla"
    if took_high:
        return "over"
    return "under"


def _apply_trick(me, opp, lead, lead_is_me, resp, resp_is_me, high_is_me):
    """Apply resolved trick; return (me, opp, next_leader_is_me, end_note)."""
    stack = [lead, resp]
    me = list(me)
    opp = list(opp)
    # Remove resp from the correct hand (lead already removed by caller).
    if resp_is_me:
        if resp in me:
            me.remove(resp)
    else:
        if resp in opp:
            opp.remove(resp)

    end_note = None
    if resp.colour != lead.colour:
        if high_is_me:
            me = list(me) + stack
            leader_is_me = True
            end_note = "you pick up"
        else:
            opp = list(opp) + stack
            leader_is_me = False
            end_note = "opp picks up"
    else:
        leader_is_me = high_is_me
        end_note = "you win trick" if high_is_me else "opp wins trick"

    if not me and not opp:
        end_note = f"{end_note}; both empty"
    elif not me:
        end_note = f"{end_note}; you empty — win"
    elif not opp:
        end_note = f"{end_note}; opp empty — you lose"
    return me, opp, leader_is_me, end_note


def _move_key(value, card, opp_hand, lead_suit=None):
    """Prefer better value; then followable suit; then lower dump tier."""
    suit = lead_suit if lead_suit is not None else card.colour
    followable = 1 if any(c.colour == suit for c in opp_hand) else 0
    return (value, followable, -dump_tier(card), -dump_value(card), card.code())


def _unique_raised(hand, moves, accounted):
    seen = []
    for raw in moves:
        card = raise_equivalence(raw, hand, moves, accounted=accounted)
        if card not in seen:
            seen.append(card)
    return seen


def _order_leads(hand, moves, accounted, opp_hand):
    """Prefer voiding opp (cannot follow), then lower dump tier."""
    candidates = _unique_raised(hand, moves, accounted)
    opp_suits = {c.colour for c in opp_hand}

    def key(card):
        followable = 1 if card.colour in opp_suits else 0
        return (followable, dump_tier(card), dump_value(card), card.code())

    return sorted(candidates, key=key)


def _order_responses(hand, moves, accounted, lead, high):
    """Prefer winning follows (beat high) first, then raise-equivalence uniques."""
    candidates = _unique_raised(hand, moves, accounted)

    def key(card):
        wins = 0
        if card.colour == lead.colour and card > high:
            wins = 1
        return (-wins, dump_tier(card), dump_value(card), card.code())

    return sorted(candidates, key=key)


def _without(hand, card):
    out = list(hand)
    out.remove(card)
    return out


def _terminal(me, opp):
    if not me and not opp:
        return _WIN
    if not me:
        return _WIN
    if not opp:
        return (-1, -len(me))
    return None


def _value_to_lead(me, opp, leader_is_me, memo, budget, alpha, beta):
    if budget.exhausted:
        return _BUDGET_FAIL
    if budget.hit():
        return _BUDGET_FAIL
    term = _terminal(me, opp)
    if term is not None:
        return term

    key = (frozenset(me), frozenset(opp), leader_is_me)
    if key in memo:
        return memo[key]

    accounted = set(me) | set(opp)
    if leader_is_me:
        moves = valid_moves(me, None)
        candidates = _order_leads(me, moves, accounted, opp)
        best = _ME_MIN
        cut = False
        for card in candidates:
            me2 = _without(me, card)
            v = _value_after_response(
                me2,
                opp,
                lead=card,
                high=card,
                high_is_me=True,
                responder_is_me=False,
                memo=memo,
                budget=budget,
                alpha=alpha,
                beta=beta,
            )
            if v > best:
                best = v
            if best > alpha:
                alpha = best
            if alpha >= beta:
                cut = True
                break
        # Only store exact values (cutoffs are bounds, unsafe to reuse).
        if not budget.exhausted and not cut:
            memo[key] = best
        return best

    moves = valid_moves(opp, None)
    candidates = _order_leads(opp, moves, accounted, me)
    best = _ME_MAX
    cut = False
    for card in candidates:
        opp2 = _without(opp, card)
        v = _value_after_response(
            me,
            opp2,
            lead=card,
            high=card,
            high_is_me=False,
            responder_is_me=True,
            memo=memo,
            budget=budget,
            alpha=alpha,
            beta=beta,
        )
        if v < best:
            best = v
        if best < beta:
            beta = best
        if alpha >= beta:
            cut = True
            break
    if not budget.exhausted and not cut:
        memo[key] = best
    return best

def _value_after_response(
    me, opp, lead, high, high_is_me, responder_is_me, memo, budget, alpha, beta
):
    """Responder chooses optimally; return value tuple for me."""
    if budget.exhausted:
        return _BUDGET_FAIL
    if budget.hit():
        return _BUDGET_FAIL
    hand = me if responder_is_me else opp
    legal = valid_moves(hand, cards_of_suit(lead.colour))
    accounted = set(me) | set(opp) | {lead}
    candidates = _order_responses(hand, legal, accounted, lead, high)

    if responder_is_me:
        best = _ME_MIN
        for card in candidates:
            me2 = _without(me, card)
            high2 = high
            high_me2 = high_is_me
            if card.colour == lead.colour and card > high2:
                high2 = card
                high_me2 = True
            v = _resolve_and_value(
                me2,
                opp,
                lead=lead,
                high=high2,
                high_is_me=high_me2,
                resp=card,
                resp_is_me=True,
                memo=memo,
                budget=budget,
                alpha=alpha,
                beta=beta,
            )
            if v > best:
                best = v
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break
        return best

    best = _ME_MAX
    for card in candidates:
        opp2 = _without(opp, card)
        high2 = high
        high_me2 = high_is_me
        if card.colour == lead.colour and card > high2:
            high2 = card
            high_me2 = False
        v = _resolve_and_value(
            me,
            opp2,
            lead=lead,
            high=high2,
            high_is_me=high_me2,
            resp=card,
            resp_is_me=False,
            memo=memo,
            budget=budget,
            alpha=alpha,
            beta=beta,
        )
        if v < best:
            best = v
        if best < beta:
            beta = best
        if alpha >= beta:
            break
    return best


def _resolve_and_value(
    me, opp, lead, high, high_is_me, resp, resp_is_me, memo, budget, alpha, beta
):
    stack = [lead, resp]
    if resp.colour != lead.colour:
        if high_is_me:
            me = list(me) + stack
            leader_is_me = True
        else:
            opp = list(opp) + stack
            leader_is_me = False
    else:
        leader_is_me = high_is_me

    term = _terminal(me, opp)
    if term is not None:
        return term
    return _value_to_lead(me, opp, leader_is_me, memo, budget, alpha, beta)
