"""Lead-card MC scoring (lose-rate + immediate self-thulla pickup)."""

from __future__ import annotations

from .constants import (
    LEAD_LIABILITY_WEIGHT,
    LEAD_PICKUP_WEIGHT,
    LEAD_SUIT_VOID_WEIGHT,
    LEAD_TIER_WEIGHT,
    LEAD_VOID_COUNT_WEIGHT,
    LOOKAHEAD_SAMPLES,
)
from .dump import dump_tier, dump_value
from .rollouts import _build_full_hands, _lead_card_then_lose, _trick1_self_pickup
from .sampling import _sample_deals, estimate_thulla_prob


def immediate_self_thulla_prob(view, my_hand, lead_card, seats_after=None, samples=LOOKAHEAD_SAMPLES):
    """P(leader picks up the pot on trick 1 via thulla after leading lead_card)."""
    seats = list(
        seats_after
        if seats_after is not None
        else view.players_after_me_this_trick()
    )
    if not seats:
        return 0.0

    suit = lead_card.colour
    if view.is_void(seats[0], suit):
        return 1.0

    me = view.me
    active = list(view.active_indices)
    hits = 0
    n = 0
    for dealt in _sample_deals(view, my_hand, samples):
        n += 1
        full = _build_full_hands(view, my_hand, dealt)
        if lead_card not in full[me]:
            continue
        hands = [list(h) for h in full]
        hands[me].remove(lead_card)
        if _trick1_self_pickup(hands, me, lead_card, active, view=view):
            hits += 1
    return hits / max(1, n)


def _lead_suit_risk(view, hand, suit, seats_after, samples=200):
    """P(thulla) and count of known voids after leader in `suit`."""
    seats = list(seats_after or view.players_after_me_this_trick())
    void_count = sum(1 for p in seats if view.is_void(p, suit))
    if void_count:
        return 1.0, void_count
    p = estimate_thulla_prob(view, suit, hand, seats_after=seats, samples=samples)
    return p, void_count


def score_lead_candidates(
    view,
    my_hand,
    candidate_cards,
    samples=LOOKAHEAD_SAMPLES,
    pickup_weight=LEAD_PICKUP_WEIGHT,
):
    """Composite lead scores: MC lose-rate + immediate self-thulla pickup penalty.

    Returns (scores, lose_rates, pickup_probs) dicts keyed by card.
    """
    if not candidate_cards:
        return {}, {}, {}
    seats = view.players_after_me_this_trick()
    if not seats:
        seats = [p for p in view.active_indices if p != view.me]
    lose_rates = estimate_lead_lose_rates(
        view, my_hand, candidate_cards, samples=samples
    )
    pickup_probs = {}
    scores = {}
    suit_risk_cache = {}
    # Pickup MC is secondary to lose-rate; keep it cheaper than the main loop.
    pickup_samples = max(8, min(samples, 12))
    for card in candidate_cards:
        suit = card.colour
        if suit not in suit_risk_cache:
            suit_risk_cache[suit] = _lead_suit_risk(
                view, my_hand, suit, seats, samples=min(samples, 80)
            )
        suit_p, void_count = suit_risk_cache[suit]
        p_pickup = immediate_self_thulla_prob(
            view, my_hand, card, seats_after=seats, samples=pickup_samples
        )
        pickup_probs[card] = p_pickup
        # Never prefer leading into a known void — MC lose noise must not override.
        if void_count:
            scores[card] = 5.0 + lose_rates.get(card, 1.0)
            pickup_probs[card] = 1.0
            continue
        face_penalty = 0.0
        if dump_value(card) > 0:
            face_penalty = p_pickup * dump_value(card) / 10.0
        dump_safe = max(0.0, 1.0 - p_pickup)
        scores[card] = (
            lose_rates.get(card, 1.0)
            + pickup_weight * p_pickup
            + pickup_weight * face_penalty
            + LEAD_SUIT_VOID_WEIGHT * suit_p
            + LEAD_VOID_COUNT_WEIGHT * void_count
            - dump_value(card) * LEAD_LIABILITY_WEIGHT * dump_safe
            - dump_tier(card) * LEAD_TIER_WEIGHT * dump_safe
        )
    return scores, lose_rates, pickup_probs


def estimate_lead_lose_rates(view, my_hand, candidate_cards, samples=24):
    """For each lead card, estimate P(finish last) via deal sampling + survival playouts.

    Returns dict card -> lose_rate.
    """
    if not candidate_cards:
        return {}
    active = list(view.active_indices)
    me = view.me
    rates = {c: 0.0 for c in candidate_cards}
    hits = {c: 0 for c in candidate_cards}
    n = 0
    for dealt in _sample_deals(view, my_hand, samples):
        n += 1
        full = _build_full_hands(view, my_hand, dealt)
        for card in candidate_cards:
            if card not in full[me]:
                continue
            hands = [list(h) for h in full]
            hands[me].remove(card)
            if _lead_card_then_lose(hands, me, card, active, view=view):
                hits[card] += 1
    if n == 0:
        return {c: 1.0 for c in candidate_cards}
    for c in candidate_cards:
        rates[c] = hits[c] / n
    return rates
