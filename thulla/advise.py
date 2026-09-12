"""Structured move advice using the same policy as ComputerPlayer (single pass)."""

from __future__ import annotations

from typing import Any

from .cards import NUMBER_CARDS, valid_moves
from .players import (
    DEFAULT_MC_SAMPLES,
    LOOKAHEAD_MAX_UNKNOWN,
    LOOKAHEAD_SAMPLES,
    THULLA_P_THRESHOLD,
    should_cpu_take,
)
from .prob import (
    _liability_score,
    case_a_should_take,
    compare_take_lose_rates,
    count_free_unknown,
    estimate_lead_lose_rates,
    estimate_thulla_prob,
)


def advise_session(session) -> dict[str, Any]:
    """Return bot-policy advice for the human seat (human mode only)."""
    if session.mode != "human":
        return {
            "available": False,
            "reason": "Ideal move is only available in human vs AI.",
        }
    if session.phase == "finished":
        return {"available": False, "phase": "finished", "reason": "Game over."}

    pending = session.pending
    if pending is None:
        return {
            "available": False,
            "phase": session.phase,
            "reason": "Waiting for the next decision.",
        }

    if pending["type"] == "reveal":
        return {
            "available": False,
            "phase": "trick_reveal",
            "reason": "Trick complete — step past the reveal.",
        }

    seat = pending.get("seat")
    if pending["type"] in ("play", "take", "give") and not session.is_human(seat):
        return {
            "available": False,
            "phase": session.phase,
            "reason": "Not your turn — waiting on a CPU.",
            "whose_turn": seat,
        }

    if pending["type"] == "play":
        return _advise_play(session)
    if pending["type"] == "take":
        return _advise_take(session)
    if pending["type"] == "give":
        return _advise_give(session)

    return {"available": False, "reason": f"No advice for pending {pending['type']}."}


def _advise_play(session) -> dict[str, Any]:
    g = session.game
    seat = session.human_seat
    assert seat is not None and session.trick is not None
    hand = list(g.players[seat].hand)
    expected = g.expected_for_seat(session.trick, seat)
    moves = valid_moves(hand, expected)
    view = g.view_for_seat(session.trick, seat)

    must_follow = bool(expected) and any(c in expected for c in hand)
    if expected is None:
        kind = "lead"
        card, steps, extra = _lead(hand, moves, view, samples=DEFAULT_MC_SAMPLES)
    elif must_follow:
        kind = "follow"
        card, steps, extra = _follow(hand, moves, view, samples=DEFAULT_MC_SAMPLES)
    else:
        kind = "thulla"
        card, steps, extra = _thulla(hand, moves, view)

    highest = view.current_highest
    return {
        "available": True,
        "phase": session.phase,
        "action": "play",
        "kind": kind,
        "recommended": {"type": "play", "card": card.code()},
        "situation": {
            "lead_suit": session.trick.colour,
            "current_highest": highest.code() if highest else None,
            "current_highest_player": view.current_highest_player,
            "must_follow": must_follow,
            "legal_moves": [c.code() for c in moves],
            "hand_size": len(hand),
            "seats_after": list(view.players_after_me_this_trick()),
        },
        "steps": steps,
        **extra,
    }


def _lead(hand, moves, view, samples):
    """Same logic as players._choose_lead, with a structured trace."""
    steps = []
    seats = view.players_after_me_this_trick()
    if not seats:
        seats = [p for p in view.active_indices if p != view.me]

    by_suit = {}
    for card in moves:
        by_suit.setdefault(card.colour, []).append(card)

    p_cache = {}

    def suit_p(suit):
        if suit in p_cache:
            return p_cache[suit]
        if any(view.is_void(p, suit) for p in seats):
            p_cache[suit] = 1.0
            return 1.0
        p = estimate_thulla_prob(view, suit, hand, seats_after=seats, samples=samples)
        p_cache[suit] = p
        return p

    suit_risks = []
    for suit in by_suit:
        p = suit_p(suit)
        note = (
            "someone after you is void"
            if p >= 1.0 and any(view.is_void(x, suit) for x in seats)
            else ("safe" if p < THULLA_P_THRESHOLD else "risky")
        )
        suit_risks.append(
            {
                "suit": suit,
                "p": round(p, 3),
                "note": note,
                "cards": [c.code() for c in sorted(by_suit[suit])],
            }
        )
        steps.append({"label": "THULLA RISK", "detail": f"{suit}: {p:.0%} — {note}"})

    no_void = [s for s in by_suit if not any(view.is_void(p, s) for p in seats)]
    candidates = no_void if no_void else list(by_suit)
    if no_void and len(no_void) < len(by_suit):
        skipped = [s for s in by_suit if s not in no_void]
        steps.append(
            {
                "label": "FILTER",
                "detail": f"Skip suits with known voids after you: {', '.join(skipped)}",
            }
        )

    def suit_key(s):
        p = suit_p(s)
        if p < THULLA_P_THRESHOLD:
            best_liab = max(_liability_score(c) for c in by_suit[s])
            return (round(p, 1), -best_liab, min(by_suit[s]))
        return (p, 0, min(by_suit[s]))

    best_suit = min(candidates, key=suit_key)
    p = suit_p(best_suit)
    cards = by_suit[best_suit]

    if p >= THULLA_P_THRESHOLD:
        choice = min(cards)
        card_rule = "high thulla risk → lead low"
    else:
        choice = max(cards, key=lambda c: (_liability_score(c), c))
        liab = _liability_score(choice)
        card_rule = (
            "safe suit → dump A/K liability" if liab else "safe suit → high card"
        )

    steps.append(
        {"label": "SUIT PICK", "detail": f"{best_suit} (p≈{p:.0%})"}
    )
    steps.append({"label": "CARD RULE", "detail": card_rule})

    lookahead = None
    if len(moves) > 1:
        unknown = count_free_unknown(view, hand)
        if unknown <= LOOKAHEAD_MAX_UNKNOWN:
            lead_opts = list({choice, max(cards), min(cards)})
            for s in candidates:
                lead_opts.append(
                    max(by_suit[s], key=lambda c: (_liability_score(c), c))
                )
            lead_opts = [c for c in dict.fromkeys(lead_opts) if c in moves]
            rates = estimate_lead_lose_rates(
                view, hand, lead_opts, samples=LOOKAHEAD_SAMPLES
            )
            if rates:
                lookahead = [
                    {"card": c.code(), "lose_rate": round(rates[c], 3)}
                    for c in sorted(rates, key=lambda c: (rates[c], c.code()))
                ]
                choice = min(
                    lead_opts,
                    key=lambda c: (
                        rates.get(c, 1.0),
                        -_liability_score(c),
                        -NUMBER_CARDS.index(c.number),
                    ),
                )
                steps.append(
                    {
                        "label": "LOOKAHEAD",
                        "detail": (
                            f"{unknown} unknowns ≤ {LOOKAHEAD_MAX_UNKNOWN}: "
                            f"lose-rate sim → {choice.code()} "
                            f"({rates[choice]:.0%} finish last)"
                        ),
                    }
                )
        else:
            steps.append(
                {
                    "label": "LOOKAHEAD",
                    "detail": f"Skipped ({unknown} unknowns > {LOOKAHEAD_MAX_UNKNOWN})",
                }
            )

    steps.append({"label": "RECOMMEND", "detail": f"Play {choice.code()}"})
    return choice, steps, {"suit_risks": suit_risks, "lookahead": lookahead}


def _follow(hand, moves, view, samples):
    """Same logic as players._choose_follow, with a structured trace."""
    steps = []
    suit = moves[0].colour
    seats = view.players_after_me_this_trick()
    p = estimate_thulla_prob(view, suit, hand, seats_after=seats, samples=samples)
    highest = view.current_highest

    steps.append(
        {
            "label": "SITUATION",
            "detail": f"Must follow {suit}"
            + (f"; current high {highest.code()}" if highest else ""),
        }
    )
    steps.append(
        {
            "label": "THULLA RISK",
            "detail": (
                f"P(void after you) ≈ {p:.0%} "
                f"({'duck hard' if p >= THULLA_P_THRESHOLD else 'softer follow'})"
            ),
        }
    )

    if p >= THULLA_P_THRESHOLD and highest is not None:
        under = [card for card in moves if card < highest]
        choice = max(under) if under else min(moves)
        steps.append(
            {
                "label": "POLICY",
                "detail": (
                    "Risk high → duck with highest under the leader"
                    if under
                    else "Risk high but nothing under → play lowest"
                ),
            }
        )
    elif highest is not None and len(hand) > 2:
        under = [card for card in moves if card < highest]
        if under:
            choice = max(under)
            steps.append(
                {
                    "label": "POLICY",
                    "detail": "Cards left → soft duck (dump high without taking lead)",
                }
            )
        else:
            choice = max(moves, key=lambda c: (_liability_score(c), c))
            steps.append(
                {
                    "label": "POLICY",
                    "detail": "Nothing under → dump liability / high",
                }
            )
    else:
        choice = max(moves, key=lambda c: (_liability_score(c), c))
        steps.append(
            {
                "label": "POLICY",
                "detail": "Few cards left → dump liability / high",
            }
        )

    if (
        len(hand) == 1
        and p >= THULLA_P_THRESHOLD
        and highest is not None
        and choice > highest
    ):
        under = [card for card in moves if card < highest]
        if under:
            choice = max(under)
            steps.append(
                {
                    "label": "LAST CARD",
                    "detail": "Sole card would take lead under high risk → duck instead",
                }
            )

    steps.append({"label": "RECOMMEND", "detail": f"Play {choice.code()}"})
    return (
        choice,
        steps,
        {
            "suit_risks": [
                {
                    "suit": suit,
                    "p": round(p, 3),
                    "note": "risky" if p >= THULLA_P_THRESHOLD else "safer",
                }
            ]
        },
    )


def _thulla(hand, moves, view):
    """Same logic as players._choose_thulla, with a structured trace."""
    steps = [
        {"label": "SITUATION", "detail": "Cannot follow — thulla dump"},
    ]
    victim = view.current_highest_player

    if victim is not None:
        punish = [card for card in moves if view.is_void(victim, card.colour)]
        if punish:
            choice = max(punish, key=lambda c: (_liability_score(c), c))
            steps.append(
                {
                    "label": "POLICY",
                    "detail": (
                        f"Victim seat {victim} void in dump suit → "
                        "punish with highest liability"
                    ),
                }
            )
            steps.append({"label": "RECOMMEND", "detail": f"Play {choice.code()}"})
            return choice, steps, {}

    liabilities = [c for c in moves if _liability_score(c) > 0]
    if liabilities:
        choice = max(liabilities, key=lambda c: (_liability_score(c), c))
        steps.append(
            {"label": "POLICY", "detail": "No void-punish → dump A/K liability"}
        )
        steps.append({"label": "RECOMMEND", "detail": f"Play {choice.code()}"})
        return choice, steps, {}

    counts = {}
    for card in hand:
        counts[card.colour] = counts.get(card.colour, 0) + 1
    short = [card for card in moves if counts.get(card.colour, 0) <= 2]
    if short:
        # Deterministic for advice (bot uses random.choice).
        choice = max(short)
        steps.append(
            {
                "label": "POLICY",
                "detail": "Shorten a thin suit (≤2 cards); advice picks max of short set",
            }
        )
    else:
        choice = max(moves)
        steps.append({"label": "POLICY", "detail": "Fallback → play highest"})

    steps.append({"label": "RECOMMEND", "detail": f"Play {choice.code()}"})
    return choice, steps, {}


def _advise_take(session) -> dict[str, Any]:
    pending = session.pending
    seat = pending["seat"]
    g = session.game
    hand = list(g.players[seat].hand)
    neighbor = pending["target"]
    n_cards = pending["n_cards"]
    i_am_leader = pending["i_am_leader"]

    remaining = [p for p in g.active_in_order(seat) if p != seat]
    g.info.sync_hands(g.players)
    view = g.info.view_for(seat, remaining)

    steps = [
        {
            "label": "SITUATION",
            "detail": (
                f"Ask {pending['target_name']} for {n_cards} cards?"
                + (" (you are leader)" if i_am_leader else " (not leader)")
            ),
        }
    ]

    if not i_am_leader:
        steps.append(
            {
                "label": "POLICY",
                "detail": "Bot never asks unless it is the take-phase leader",
            }
        )
        steps.append({"label": "RECOMMEND", "detail": "Decline"})
        return {
            "available": True,
            "phase": session.phase,
            "action": "take",
            "kind": "take",
            "recommended": {"type": "take", "accept": False},
            "situation": {
                "target": neighbor,
                "target_name": pending["target_name"],
                "n_cards": n_cards,
                "i_am_leader": False,
            },
            "steps": steps,
        }

    case_a = case_a_should_take(view, hand, neighbor)
    steps.append(
        {
            "label": "CASE A",
            "detail": (
                "Neighbor void in a suit you hold, or ≥½ known cards fill your voids"
                if case_a
                else "No clear void / known-card reason to take"
            ),
        }
    )

    accept = should_cpu_take(
        hand, view, neighbor, i_am_leader, allow_late_take=True
    )

    active_n = len(view.active_indices)
    unknown = count_free_unknown(view, hand)
    if active_n == 3 and unknown <= 8:
        others = [
            p for p in view.active_indices if p != view.me and p != neighbor
        ]
        if len(others) == 1:
            lose_keep, lose_merge = compare_take_lose_rates(
                view, hand, neighbor, others[0], samples=40
            )
            steps.append(
                {
                    "label": "ENDGAME MC",
                    "detail": (
                        f"3 left, {unknown} unknowns — "
                        f"lose keep {lose_keep:.0%} vs merge {lose_merge:.0%} "
                        f"(take if merge+10% < keep)"
                    ),
                }
            )

    steps.append(
        {
            "label": "RECOMMEND",
            "detail": "Ask / take" if accept else "Decline",
        }
    )
    return {
        "available": True,
        "phase": session.phase,
        "action": "take",
        "kind": "take",
        "recommended": {"type": "take", "accept": accept},
        "situation": {
            "target": neighbor,
            "target_name": pending["target_name"],
            "n_cards": n_cards,
            "i_am_leader": True,
            "case_a": case_a,
        },
        "steps": steps,
    }


def _advise_give(session) -> dict[str, Any]:
    pending = session.pending
    steps = [
        {
            "label": "SITUATION",
            "detail": (
                f"{pending['asker_name']} asks for your {pending['n_cards']} cards"
            ),
        },
        {
            "label": "POLICY",
            "detail": "Bot always consents to give (default)",
        },
        {"label": "RECOMMEND", "detail": "Give"},
    ]
    return {
        "available": True,
        "phase": session.phase,
        "action": "give",
        "kind": "give",
        "recommended": {"type": "give", "accept": True},
        "situation": {
            "asker": pending["asker"],
            "asker_name": pending["asker_name"],
            "n_cards": pending["n_cards"],
        },
        "steps": steps,
    }
