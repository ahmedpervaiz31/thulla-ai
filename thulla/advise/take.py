"""Take / give Ideal Move advice."""

from __future__ import annotations

from typing import Any

from ..players import should_cpu_take
from ..prob import (
    TAKE_MARGIN,
    TAKE_MARGIN_SAFE_FACE,
    TAKE_UNKNOWN_MAX,
    case_a_should_take,
    compare_take_lose_rates,
    count_free_unknown,
    has_dump_safe_face_lead,
    mono_suit_feeder_should_take,
)


def advise_take(session) -> dict[str, Any]:
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
    feeder = mono_suit_feeder_should_take(view, hand, neighbor)
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
    if feeder:
        steps.append(
            {
                "label": "FEEDER TRAP",
                "detail": (
                    "Neighbor is mono-suit, a later seat voids that suit, and you "
                    "already hold it — playing on leaks their cards via public "
                    "thullas; taking merges privately (same cards, no info leak)"
                ),
            }
        )

    unknown = count_free_unknown(view, hand)
    active_n = len(view.active_indices)
    lose_keep = lose_merge = None
    if feeder:
        steps.append(
            {
                "label": "P(LAST) MC",
                "detail": "Skipped — feeder/info-leak pattern → ask",
            }
        )
    elif active_n >= 3 and unknown <= TAKE_UNKNOWN_MAX:
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


def advise_give(session) -> dict[str, Any]:
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
            "detail": (
                "Always give — handing over finishes you (you are out), "
                "so you cannot finish last"
            ),
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
