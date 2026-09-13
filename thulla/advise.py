"""Structured move advice using the same policy as ComputerPlayer (single pass)."""

from __future__ import annotations

from typing import Any

from .cards import NUMBER_CARDS, valid_moves
from .players import (
    DEFAULT_MC_SAMPLES,
    LOOKAHEAD_MAX_UNKNOWN,
    LOOKAHEAD_SAMPLES,
    THULLA_P_THRESHOLD,
    _play_equiv,
    should_cpu_take,
)
from .prob import (
    TAKE_MARGIN,
    TAKE_MARGIN_SAFE_FACE,
    TAKE_UNKNOWN_MAX,
    case_a_should_take,
    compare_take_lose_rates,
    count_free_unknown,
    dump_tier,
    dump_value,
    estimate_lead_lose_rates,
    estimate_thulla_prob,
    follow_take_safe,
    has_dump_safe_face_lead,
    is_face,
    is_keeper,
    suit_dump_safe,
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
        safe = suit_dump_safe(
            view, hand, suit, seats, p_thulla=p, threshold=THULLA_P_THRESHOLD
        )
        if p >= 1.0 and any(view.is_void(x, suit) for x in seats):
            note = "someone after you is void"
        elif safe:
            note = "lead dump-safe"
        elif p < THULLA_P_THRESHOLD:
            note = "risky shape/discards"
        else:
            note = "risky"
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

    safe_suits = [
        s
        for s in candidates
        if suit_dump_safe(
            view, hand, s, seats, p_thulla=suit_p(s), threshold=THULLA_P_THRESHOLD
        )
    ]

    def best_in_suit(s):
        return max(by_suit[s], key=lambda c: (dump_tier(c), dump_value(c), c))

    def low_in_suit(s):
        cards = by_suit[s]
        non_keepers = [c for c in cards if not is_keeper(c)]
        pool = non_keepers if non_keepers else cards
        return min(pool)

    high_tier = [c for c in moves if dump_tier(c) >= 1]

    if safe_suits:
        def suit_key(s):
            best = best_in_suit(s)
            return (-dump_tier(best), len(by_suit[s]), -dump_value(best))

        best_suit = min(safe_suits, key=suit_key)
        choice = best_in_suit(best_suit)
        card_rule = (
            f"lead dump-safe → tier/short ({choice.code()}, "
            f"tier {dump_tier(choice)}, len {len(by_suit[best_suit])})"
        )
    else:
        def risk_key(s):
            return (suit_p(s), len(by_suit[s]), min(by_suit[s]))

        best_suit = min(candidates, key=risk_key)
        p = suit_p(best_suit)
        if p >= THULLA_P_THRESHOLD:
            raw = low_in_suit(best_suit)
            choice = _play_equiv(raw, hand, moves, view)
            card_rule = (
                "high thulla risk → lead low (prefer non-keeper)"
                if choice == raw
                else f"high thulla risk → equiv-raise {raw.code()}→{choice.code()}"
            )
        else:
            choice = best_in_suit(best_suit)
            card_rule = "no lead dump-safe suit → best available dump"

    if high_tier and dump_tier(choice) == 0:
        safe_high = [c for c in high_tier if c.colour in safe_suits]
        pool = safe_high if safe_high else high_tier
        choice = max(
            pool,
            key=lambda c: (dump_tier(c), -len(by_suit[c.colour]), dump_value(c), c),
        )
        card_rule = f"block keeper lead → {choice.code()}"

    choice = _play_equiv(choice, hand, moves, view)
    p = suit_p(best_suit)

    steps.append(
        {"label": "SUIT PICK", "detail": f"{best_suit} (p≈{p:.0%})"}
    )
    steps.append({"label": "CARD RULE", "detail": card_rule})

    lookahead = None
    if len(moves) > 1:
        unknown = count_free_unknown(view, hand)
        if unknown <= LOOKAHEAD_MAX_UNKNOWN:
            lead_opts = [choice, low_in_suit(best_suit), best_in_suit(best_suit)]
            for s in candidates:
                lead_opts.append(best_in_suit(s))
                lead_opts.append(low_in_suit(s))
            lead_opts.extend(high_tier)
            lead_opts = [
                _play_equiv(c, hand, moves, view)
                for c in dict.fromkeys(lead_opts)
                if c in moves
            ]
            lead_opts = list(dict.fromkeys(lead_opts))
            if any(dump_tier(c) >= 1 for c in lead_opts):
                lead_opts = [c for c in lead_opts if dump_tier(c) >= 1] or lead_opts
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
                        -dump_tier(c),
                        -dump_value(c),
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

    choice = _play_equiv(choice, hand, moves, view)
    steps.append({"label": "RECOMMEND", "detail": f"Play {choice.code()}"})
    return choice, steps, {"suit_risks": suit_risks, "lookahead": lookahead}


def _follow(hand, moves, view, samples):
    """Same logic as players._choose_follow, with a structured trace."""
    steps = []
    suit = moves[0].colour
    seats = view.players_after_me_this_trick()
    p = estimate_thulla_prob(view, suit, hand, seats_after=seats, samples=samples)
    highest = view.current_highest
    winners = [c for c in moves if highest is None or c > highest]
    under = [c for c in moves if highest is not None and c < highest]
    take_ok = follow_take_safe(
        view, hand, suit, seats, p_thulla=p, threshold=THULLA_P_THRESHOLD
    )
    face_winners = [c for c in winners if is_face(c)]

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
                f"P(void after you) ≈ {p:.0%}; "
                f"follow-take safe={take_ok} (void risk only)"
            ),
        }
    )

    if p >= THULLA_P_THRESHOLD and highest is not None:
        if under:
            choice = max(under, key=lambda c: (dump_tier(c), dump_value(c), c))
            steps.append(
                {
                    "label": "POLICY",
                    "detail": "Risk high → duck; dump best under (faces > mids > keepers)",
                }
            )
        else:
            choice = min(moves)
            steps.append(
                {
                    "label": "POLICY",
                    "detail": "Risk high but nothing under → play lowest",
                }
            )
    elif face_winners and take_ok:
        choice = max(face_winners, key=lambda c: (dump_value(c), c))
        steps.append(
            {
                "label": "POLICY",
                "detail": "Follow-cash → take with best face among winners",
            }
        )
    elif winners and take_ok:
        choice = max(winners, key=lambda c: (dump_tier(c), dump_value(c), c))
        steps.append(
            {
                "label": "POLICY",
                "detail": "Follow-cash → take with best dump among winners",
            }
        )
    elif under:
        choice = max(under, key=lambda c: (dump_tier(c), dump_value(c), c))
        steps.append(
            {
                "label": "POLICY",
                "detail": "Do not take → dump best under (keep 2–5)",
            }
        )
    elif winners:
        choice = min(winners)
        steps.append(
            {
                "label": "POLICY",
                "detail": "Must win but not take-safe → lowest winner",
            }
        )
    else:
        choice = max(moves, key=lambda c: (dump_tier(c), dump_value(c), c))
        steps.append(
            {
                "label": "POLICY",
                "detail": "Fallback → best dump value",
            }
        )

    if (
        len(hand) == 1
        and p >= THULLA_P_THRESHOLD
        and highest is not None
        and choice > highest
    ):
        if under:
            choice = max(under, key=lambda c: (dump_tier(c), dump_value(c), c))
            steps.append(
                {
                    "label": "LAST CARD",
                    "detail": "Sole card would take lead under high risk → duck instead",
                }
            )

    raw = choice
    choice = _play_equiv(choice, hand, moves, view)
    if choice != raw:
        steps.append(
            {
                "label": "EQUIV",
                "detail": f"{raw.code()} → {choice.code()} (same class — play high)",
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
                    "note": "follow-take safe" if take_ok else "risky",
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
            choice = _play_equiv(
                max(punish, key=lambda c: (dump_tier(c), dump_value(c), c)),
                hand,
                moves,
                view,
            )
            steps.append(
                {
                    "label": "POLICY",
                    "detail": (
                        f"Victim seat {victim} void in dump suit → "
                        "punish with highest dump tier"
                    ),
                }
            )
            steps.append({"label": "RECOMMEND", "detail": f"Play {choice.code()}"})
            return choice, steps, {}

    faces = [c for c in moves if is_face(c)]
    if faces:
        choice = _play_equiv(
            max(faces, key=lambda c: (dump_value(c), c)),
            hand,
            moves,
            view,
        )
        steps.append(
            {"label": "POLICY", "detail": "No void-punish → dump A/K/Q/J"}
        )
        steps.append({"label": "RECOMMEND", "detail": f"Play {choice.code()}"})
        return choice, steps, {}

    counts = {}
    for card in hand:
        counts[card.colour] = counts.get(card.colour, 0) + 1
    non_keepers = [c for c in moves if not is_keeper(c)]
    pool = non_keepers if non_keepers else list(moves)
    short = [card for card in pool if counts.get(card.colour, 0) <= 2]
    if short:
        choice = _play_equiv(
            max(short, key=lambda c: (dump_tier(c), dump_value(c), c)),
            hand,
            moves,
            view,
        )
        steps.append(
            {
                "label": "POLICY",
                "detail": "Shorten a thin suit; mids before keepers",
            }
        )
    else:
        choice = _play_equiv(
            max(pool, key=lambda c: (dump_tier(c), dump_value(c), c)),
            hand,
            moves,
            view,
        )
        steps.append({"label": "POLICY", "detail": "Fallback → best dump value"})

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
    safe_face = has_dump_safe_face_lead(view, hand)
    steps.append(
        {
            "label": "CASE A",
            "detail": (
                "Soft hint: small hand + useful voids (not an auto-take)"
                if case_a
                else "No soft void/small-hand merge hint"
            ),
        }
    )

    unknown = count_free_unknown(view, hand)
    active_n = len(view.active_indices)
    lose_keep = lose_merge = None
    if active_n >= 3 and unknown <= TAKE_UNKNOWN_MAX:
        lose_keep, lose_merge = compare_take_lose_rates(
            view, hand, neighbor, samples=40
        )
        margin = TAKE_MARGIN_SAFE_FACE if safe_face else TAKE_MARGIN
        steps.append(
            {
                "label": "P(LAST) MC",
                "detail": (
                    f"{active_n} active, {unknown} unknowns — "
                    f"lose keep {lose_keep:.0%} vs merge {lose_merge:.0%} "
                    f"(take if merge+{margin:.0%} < keep"
                    + ("; safer margin — face lead left)" if safe_face else ")")
                ),
            }
        )
    else:
        steps.append(
            {
                "label": "P(LAST) MC",
                "detail": (
                    f"Skipped (need ≥3 active and unknowns ≤ {TAKE_UNKNOWN_MAX}; "
                    f"have {active_n} active, {unknown} unknowns) → refuse"
                ),
            }
        )

    accept = should_cpu_take(
        hand, view, neighbor, i_am_leader, allow_late_take=True
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
            "lose_keep": lose_keep,
            "lose_merge": lose_merge,
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
