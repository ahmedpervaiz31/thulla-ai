"""Thulla-dump MC shortlist, outcomes, and composite scoring."""

from __future__ import annotations

from .constants import (
    LOOKAHEAD_SAMPLES,
    THULLA_ESCAPE_HORIZON,
    THULLA_ESCAPE_LIVE,
    THULLA_ESCAPE_WEIGHT,
    THULLA_FULL_LOSE_MAX_UNKNOWN,
    THULLA_LIABILITY_WEIGHT,
    THULLA_LOSE_MAX_TRICKS,
    THULLA_MC_MAX_CANDIDATES,
    THULLA_SHED_WEIGHT,
)
from .dump import dump_tier, dump_value
from .rollouts import _build_full_hands, _n_player_i_lose, _survival_trick_once
from .sampling import _sample_deals, count_free_unknown


def _resolve_thulla_dump(hands, me_idx, dump_card, view):
    """Apply mid-trick thulla dump: pot (trick + dump) goes to current highest; they lead.

    Real rules end the trick on the first off-suit play — seats after the dumper do not act.
    Returns (victim_idx, leader_idx).
    """
    victim = view.current_highest_player
    if victim is None:
        raise ValueError("thulla dump requires a current highest player")
    if dump_card not in hands[me_idx]:
        raise ValueError("dump card missing from hand")
    hands[me_idx].remove(dump_card)
    stack = list(view._info.trick_cards) + [dump_card]
    hands[victim].extend(stack)
    return victim, victim


def _thulla_dump_then_outcomes(
    hands,
    me_idx,
    dump_card,
    view,
    horizon=THULLA_ESCAPE_HORIZON,
    max_tricks=THULLA_LOSE_MAX_TRICKS,
    full_lose=True,
):
    """After dumping dump_card: (i_lose, victim_away_soon, card_shed_soon).

    When full_lose is False, skip remaining-game survival (i_lose stays False)
    and only measure short-horizon away/shed — much cheaper early/mid game.
    """
    victim, leader = _resolve_thulla_dump(hands, me_idx, dump_card, view)
    victim_away_soon = not bool(hands[victim])
    card_shed_soon = False
    track = dump_card

    for _ in range(horizon):
        active = [i for i in range(len(hands)) if hands[i]]
        if len(active) <= 1:
            break
        if not hands[victim]:
            victim_away_soon = True
            break
        leader, discarded, _thulla = _survival_trick_once(hands, leader)
        if discarded is not None and track in discarded:
            card_shed_soon = True
        if not hands[victim]:
            victim_away_soon = True

    if not full_lose:
        return False, victim_away_soon, card_shed_soon

    survivors = [i for i in range(len(hands)) if hands[i]]
    if len(survivors) <= 1:
        i_lose = len(survivors) == 1 and survivors[0] == me_idx
    else:
        i_lose = _n_player_i_lose(
            hands, me_idx, leader, max_tricks=max_tricks, use_survival=True
        )
    return i_lose, victim_away_soon, card_shed_soon


def estimate_thulla_dump_outcomes(
    view,
    my_hand,
    candidate_cards,
    samples=LOOKAHEAD_SAMPLES,
    horizon=THULLA_ESCAPE_HORIZON,
    full_lose=True,
):
    """Per dump card: lose_rate, p_victim_away_soon, p_card_shed_soon."""
    if not candidate_cards:
        return {}, {}, {}
    me = view.me
    lose_hits = {c: 0 for c in candidate_cards}
    away_hits = {c: 0 for c in candidate_cards}
    shed_hits = {c: 0 for c in candidate_cards}
    n = 0
    for dealt in _sample_deals(view, my_hand, samples):
        n += 1
        full = _build_full_hands(view, my_hand, dealt)
        for card in candidate_cards:
            if card not in full[me]:
                continue
            hands = [list(h) for h in full]
            i_lose, away, shed = _thulla_dump_then_outcomes(
                hands, me, card, view, horizon=horizon, full_lose=full_lose
            )
            if i_lose:
                lose_hits[card] += 1
            if away:
                away_hits[card] += 1
            if shed:
                shed_hits[card] += 1
    if n == 0:
        return (
            {c: 1.0 for c in candidate_cards},
            {c: 0.0 for c in candidate_cards},
            {c: 0.0 for c in candidate_cards},
        )
    lose_rates = {c: lose_hits[c] / n for c in candidate_cards}
    p_away = {c: away_hits[c] / n for c in candidate_cards}
    p_shed = {c: shed_hits[c] / n for c in candidate_cards}
    return lose_rates, p_away, p_shed


def shortlist_thulla_candidates(view, my_hand, candidates, max_n=THULLA_MC_MAX_CANDIDATES):
    """Keep dump MC cheap: diversify suits, prefer void-punish and liability extremes."""
    opts = list(candidates)
    if len(opts) <= max_n:
        return opts
    victim = view.current_highest_player
    counts = {}
    for c in my_hand:
        counts[c.colour] = counts.get(c.colour, 0) + 1

    def rank_key(card):
        void_hit = (
            0
            if victim is not None and view.is_void(victim, card.colour)
            else 1
        )
        creates_void = 0 if counts.get(card.colour, 0) == 1 else 1
        extreme = -abs(dump_value(card))
        return (void_hit, creates_void, extreme, -dump_tier(card), card.code())

    ranked = sorted(opts, key=rank_key)
    picked = []
    seen_suits = set()
    for card in ranked:
        if card.colour in seen_suits:
            continue
        picked.append(card)
        seen_suits.add(card.colour)
        if len(picked) >= max_n:
            return picked
    for card in ranked:
        if card in picked:
            continue
        picked.append(card)
        if len(picked) >= max_n:
            break
    return picked


def score_thulla_candidates(
    view,
    my_hand,
    candidate_cards,
    samples=LOOKAHEAD_SAMPLES,
    escape_weight=THULLA_ESCAPE_WEIGHT,
    shed_weight=THULLA_SHED_WEIGHT,
    horizon=THULLA_ESCAPE_HORIZON,
    full_lose=None,
):
    """Composite thulla-dump scores (lower better).

    When escape looks live (victim near empty or max away ≥ threshold):
      score = lose_rate + escape_weight * away + shed_weight * shed
    Otherwise mid-game defaults to liability dumps (faces > mids > keepers):
      score = lose_rate - liability_weight * dump_value/10
      (shed weight off so sticky keepers do not beat A/K/Q)

    When full_lose is None, enable full-game lose rollouts only if
    free unknowns ≤ THULLA_FULL_LOSE_MAX_UNKNOWN.
    """
    if not candidate_cards:
        return {}, {}, {}
    if full_lose is None:
        full_lose = count_free_unknown(view, my_hand) <= THULLA_FULL_LOSE_MAX_UNKNOWN
    lose_rates, p_away, p_shed = estimate_thulla_dump_outcomes(
        view,
        my_hand,
        candidate_cards,
        samples=samples,
        horizon=horizon,
        full_lose=full_lose,
    )
    scores = {}
    extras = {}
    counts = {}
    for c in my_hand:
        counts[c.colour] = counts.get(c.colour, 0) + 1
    victim = view.current_highest_player
    victim_size = view.hand_size(victim) if victim is not None else 99
    max_away = max(p_away.values(), default=0.0)
    escape_live = max_away >= THULLA_ESCAPE_LIVE or victim_size <= horizon + 1
    sw = shed_weight if escape_live else 0.0
    liability_w = 0.0 if escape_live else THULLA_LIABILITY_WEIGHT
    for card in candidate_cards:
        lr = lose_rates.get(card, 1.0) if full_lose else 0.0
        away = p_away.get(card, 0.0)
        shed = p_shed.get(card, 0.0)
        scores[card] = (
            lr
            + escape_weight * away
            + sw * shed
            - liability_w * dump_value(card) / 10.0
        )
        extras[card] = {
            "lose_rate": lr,
            "p_victim_away_soon": away,
            "p_card_shed_soon": shed,
            "creates_void": counts.get(card.colour, 0) == 1,
            "victim_void_suit": bool(
                victim is not None and view.is_void(victim, card.colour)
            ),
            "full_lose": full_lose,
            "escape_live": escape_live,
        }
    return scores, lose_rates, extras


def thulla_dump_score_key(card, scores, extras=None):
    """Lower is better. Ties: my void, low shed, victim void suit, then dump_value."""
    extras = extras or {}
    info = extras.get(card) or {}
    return (
        scores.get(card, 1.0),
        0 if info.get("creates_void") else 1,
        info.get("p_card_shed_soon", 0.0),
        0 if info.get("victim_void_suit") else 1,
        -dump_value(card),
        card.code(),
    )
