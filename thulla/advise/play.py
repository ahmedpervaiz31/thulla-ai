"""Play-card Ideal Move: bot chooser + explanation steps."""

from __future__ import annotations

from typing import Any

from ..cards import valid_moves
from ..heads_up import exact_principal_line, try_exact_with_value_from_view
from ..players import (
    DEFAULT_MC_SAMPLES,
    LOOKAHEAD_MAX_UNKNOWN,
    _choose_follow,
    _choose_lead,
    _choose_thulla,
    _lead_mc_samples,
    _lead_mc_shortlist,
    _lead_score_key,
    _play_equiv,
    _thulla_mc_samples,
)
from ..prob import (
    DUMP_SAFE_P_THRESHOLD,
    THULLA_MC_MAX_CANDIDATES,
    any_keeper_duck_after,
    count_free_unknown,
    dump_tier,
    dump_value,
    estimate_thulla_prob,
    follow_take_safe,
    is_face,
    score_lead_candidates,
    score_thulla_candidates,
    shortlist_thulla_candidates,
    suit_dump_safe,
    thulla_dump_score_key,
)


def advise_play(session) -> dict[str, Any]:
    g = session.game
    pending = session.pending
    assert pending is not None and pending.get("type") == "play"
    seat = pending["seat"]
    assert session.trick is not None
    hand = list(g.players[seat].hand)
    expected = g.expected_for_seat(session.trick, seat)
    moves = valid_moves(hand, expected)
    view = g.view_for_seat(session.trick, seat)

    must_follow = bool(expected) and any(c in expected for c in hand)
    if expected is None:
        kind = "lead"
    elif must_follow:
        kind = "follow"
    else:
        kind = "thulla"

    exact_card, exact_value = try_exact_with_value_from_view(
        hand, moves, expected, view
    )
    if exact_card is not None:
        outcome = exact_value[0] if exact_value is not None else None
        opp = view.heads_up_opponent()
        deduced = view.deduced_hand(opp, hand) if opp is not None else None
        line = []
        if deduced is not None:
            if expected is None:
                line = exact_principal_line(
                    hand,
                    deduced,
                    i_am_leader=True,
                    first_card=exact_card,
                    max_ms=None,
                )
            else:
                line = exact_principal_line(
                    hand,
                    deduced,
                    i_am_leader=False,
                    lead_card=expected[0],
                    highest=view.current_highest,
                    first_card=exact_card,
                    max_ms=None,
                )
        card, steps, extra = _exact_advice(exact_card, kind, outcome, line)
    elif expected is None:
        card = _choose_lead(hand, moves, view, samples=DEFAULT_MC_SAMPLES)
        steps, extra = _explain_lead(hand, moves, view, DEFAULT_MC_SAMPLES, card)
    elif must_follow:
        card = _choose_follow(hand, moves, view, samples=DEFAULT_MC_SAMPLES)
        steps, extra = _explain_follow(hand, moves, view, DEFAULT_MC_SAMPLES, card)
    else:
        card = _choose_thulla(hand, moves, view)
        steps, extra = _explain_thulla(hand, moves, view, card)

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


def _exact_advice(card, kind, outcome, line=None):
    """Build advise steps from a completed exact search (no second search)."""
    steps = [
        {
            "label": "SITUATION",
            "detail": f"Heads-up complete info — exact 1v1 search ({kind})",
        }
    ]
    if outcome == 1:
        steps.append({"label": "EXACT 1v1", "detail": "Force win with optimal play"})
    elif outcome == -1:
        steps.append(
            {
                "label": "EXACT 1v1",
                "detail": "Losing — minimize leftover cards (stay ready for a blunder)",
            }
        )
    else:
        steps.append({"label": "EXACT 1v1", "detail": f"Play {card.code()}"})

    line = line or []
    if line:
        parts = []
        for step in line:
            if not step.get("card"):
                parts.append(step.get("note") or "")
                continue
            who = "You" if step.get("side") == "you" else "Opp"
            note = step.get("note") or ""
            parts.append(f"{who} {step['card']}" + (f" ({note})" if note else ""))
        steps.append({"label": "LINE", "detail": " → ".join(parts)})

    steps.append({"label": "RECOMMEND", "detail": f"Play {card.code()}"})
    extra = {"exact_1v1": True, "outcome": outcome}
    if line:
        extra["exact_line"] = line
    return card, steps, extra


def _explain_lead(hand, moves, view, samples, choice):
    """Explain a lead already chosen by `_choose_lead`."""
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

    def void_count_after(suit):
        return sum(1 for p in seats if view.is_void(p, suit))

    suit_risks = []
    for suit in by_suit:
        p = suit_p(suit)
        voids = void_count_after(suit)
        safe = suit_dump_safe(
            view, hand, suit, seats, p_thulla=p, threshold=DUMP_SAFE_P_THRESHOLD
        )
        if voids:
            note = f"{voids} known void(s) after you"
        elif any_keeper_duck_after(view, seats, suit):
            note = "keeper duck → treat near-void"
        elif safe:
            note = "lead dump-safe"
        elif p < DUMP_SAFE_P_THRESHOLD:
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

    lead_opts = list(
        dict.fromkeys(_play_equiv(c, hand, moves, view) for c in moves)
    )
    unknown = count_free_unknown(view, hand)
    lookahead = None

    if len(lead_opts) > 1 and unknown <= LOOKAHEAD_MAX_UNKNOWN:
        shortlist = _lead_mc_shortlist(lead_opts, view)
        scores, lose_rates, pickup_probs = score_lead_candidates(
            view, hand, shortlist, samples=_lead_mc_samples(unknown)
        )
        if scores:
            lookahead = [
                {
                    "card": c.code(),
                    "lose_rate": round(lose_rates.get(c, 1.0), 3),
                    "pickup_prob": round(pickup_probs.get(c, 0.0), 3),
                    "score": round(scores[c], 3),
                }
                for c in sorted(
                    shortlist, key=lambda c: _lead_score_key(c, scores, pickup_probs)
                )
            ]
            best = lookahead[0]
            steps.append(
                {
                    "label": "SCORE",
                    "detail": (
                        f"{unknown} unknowns ≤ {LOOKAHEAD_MAX_UNKNOWN}: "
                        f"{best['card']} score={best['score']:.2f} "
                        f"(lose {best['lose_rate']:.0%}, "
                        f"self-pickup {best['pickup_prob']:.0%})"
                    ),
                }
            )
            top = lookahead[: min(5, len(lookahead))]
            steps.append(
                {
                    "label": "LOOKAHEAD",
                    "detail": "; ".join(
                        f"{row['card']}={row['score']:.2f}" for row in top
                    ),
                }
            )
    elif len(lead_opts) > 1:
        steps.append(
            {
                "label": "LOOKAHEAD",
                "detail": f"Heuristic fallback ({unknown} unknowns > {LOOKAHEAD_MAX_UNKNOWN})",
            }
        )
        steps.append(
            {"label": "POLICY", "detail": f"Heuristic lead → {choice.code()}"}
        )

    steps.append({"label": "RECOMMEND", "detail": f"Play {choice.code()}"})
    return steps, {"suit_risks": suit_risks, "lookahead": lookahead}


def _explain_follow(hand, moves, view, samples, choice):
    """Explain a follow already chosen by `_choose_follow`."""
    steps = []
    suit = moves[0].colour
    seats = view.players_after_me_this_trick()
    p = estimate_thulla_prob(view, suit, hand, seats_after=seats, samples=samples)
    highest = view.current_highest
    winners = [c for c in moves if highest is None or c > highest]
    under = [c for c in moves if highest is not None and c < highest]
    take_ok = follow_take_safe(
        view, hand, suit, seats, p_thulla=p, threshold=DUMP_SAFE_P_THRESHOLD
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

    if p >= DUMP_SAFE_P_THRESHOLD and highest is not None:
        if under:
            steps.append(
                {
                    "label": "POLICY",
                    "detail": "Risk high → duck; dump best under (faces > mids > keepers)",
                }
            )
        else:
            steps.append(
                {
                    "label": "POLICY",
                    "detail": "Risk high but nothing under → play lowest",
                }
            )
    elif face_winners and take_ok:
        steps.append(
            {
                "label": "POLICY",
                "detail": "Follow-cash → take with best face among winners",
            }
        )
    elif winners and take_ok:
        steps.append(
            {
                "label": "POLICY",
                "detail": "Follow-cash → take with best dump among winners",
            }
        )
    elif under:
        steps.append(
            {
                "label": "POLICY",
                "detail": "Do not take → dump best under (keep 2–5)",
            }
        )
    elif winners:
        steps.append(
            {
                "label": "POLICY",
                "detail": "Must win but not take-safe → lowest winner",
            }
        )
    else:
        steps.append(
            {
                "label": "POLICY",
                "detail": "Fallback → best dump value",
            }
        )

    if (
        len(hand) == 1
        and p >= DUMP_SAFE_P_THRESHOLD
        and highest is not None
        and choice > highest
        and under
    ):
        steps.append(
            {
                "label": "LAST CARD",
                "detail": "Sole card would take lead under high risk → duck instead",
            }
        )

    # Equiv raise is already applied inside the chooser; note if any equal-class mate exists.
    raw_under = None
    if under and choice in under:
        raw_under = max(under, key=lambda c: (dump_tier(c), dump_value(c), c))
        raised = _play_equiv(raw_under, hand, moves, view)
        if raised != raw_under and raised == choice:
            steps.append(
                {
                    "label": "EQUIV",
                    "detail": f"{raw_under.code()} → {choice.code()} (same class — play high)",
                }
            )

    steps.append({"label": "RECOMMEND", "detail": f"Play {choice.code()}"})
    return (
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


def _explain_thulla(hand, moves, view, choice):
    """Explain a thulla dump already chosen by `_choose_thulla`."""
    steps = [
        {"label": "SITUATION", "detail": "Cannot follow — thulla dump"},
    ]
    opts = list(dict.fromkeys(_play_equiv(c, hand, moves, view) for c in moves))
    if not opts:
        raise ValueError("no legal thulla dumps")

    unknown = count_free_unknown(view, hand)
    n_samples = _thulla_mc_samples(unknown)
    shortlist = shortlist_thulla_candidates(
        view, hand, opts, max_n=THULLA_MC_MAX_CANDIDATES
    )
    scores, lose_rates, extras = score_thulla_candidates(
        view, hand, shortlist, samples=n_samples
    )

    ranked = sorted(shortlist, key=lambda c: thulla_dump_score_key(c, scores, extras))
    dump_rows = []
    choice_info = extras.get(choice) or {}
    escape_live = bool(choice_info.get("escape_live"))
    if choice_info.get("full_lose"):
        mode = "full lose+away+shed" if escape_live else "full lose+liability"
    else:
        mode = "away+shed only" if escape_live else "liability dump"
    steps.append(
        {
            "label": "MC BUDGET",
            "detail": f"{n_samples} deals × {len(shortlist)} cards ({mode}; {unknown} unknowns)",
        }
    )
    for c in ranked[:6]:
        info = extras.get(c) or {}
        dump_rows.append(
            {
                "card": c.code(),
                "score": round(scores.get(c, 1.0), 3),
                "lose_rate": round(lose_rates.get(c, 1.0), 3),
                "p_victim_away_soon": round(info.get("p_victim_away_soon", 0.0), 3),
                "p_card_shed_soon": round(info.get("p_card_shed_soon", 0.0), 3),
                "creates_void": bool(info.get("creates_void")),
            }
        )
        score_s = f"{scores.get(c, 1.0):.2f}"
        lose_s = f"{lose_rates.get(c, 1.0):.0%}"
        away_s = f"{info.get('p_victim_away_soon', 0.0):.0%}"
        shed_s = f"{info.get('p_card_shed_soon', 0.0):.0%}"
        void_s = " void+" if info.get("creates_void") else ""
        steps.append(
            {
                "label": "DUMP MC",
                "detail": (
                    f"{c.code()}: score={score_s} lose={lose_s} "
                    f"away≈{away_s} shed≈{shed_s}{void_s}"
                ),
            }
        )

    best_info = extras.get(choice) or {}
    if not best_info.get("escape_live", True):
        reason = "dump liability (faces > mids > keepers) — escape not live"
    elif best_info.get("p_victim_away_soon", 0) >= 0.35:
        reason = "escape risk priced in — still best lose/away score"
    elif best_info.get("p_card_shed_soon", 0) <= 0.25:
        reason = "sticky dump — low chance victim sheds clean soon"
    elif best_info.get("creates_void"):
        reason = "finishes a suit void while keeping lose/away low"
    else:
        reason = "lowest lose-rate + victim-away score"
    steps.append({"label": "POLICY", "detail": reason})
    steps.append({"label": "RECOMMEND", "detail": f"Play {choice.code()}"})
    return steps, {"thulla_dump": dump_rows}


