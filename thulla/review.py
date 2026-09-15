"""Structured play review for bot analysis (ongoing + completed exports)."""

from __future__ import annotations

from typing import Any


def new_review(mode: str, names: list[str]) -> dict[str, Any]:
    return {
        "mode": mode,
        "players": list(names),
        "opening_hands": None,
        "tricks": [],
        "takes": [],
        "advice_requests": [],
    }


def compact_advice(advice: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep Ideal Move payload scannable (drop bulky situation duplicates)."""
    if not advice or not advice.get("available"):
        return None
    out: dict[str, Any] = {
        "action": advice.get("action"),
        "kind": advice.get("kind"),
        "recommended": advice.get("recommended"),
        "steps": advice.get("steps") or [],
    }
    if advice.get("suit_risks"):
        out["suit_risks"] = advice["suit_risks"]
    if advice.get("lookahead"):
        out["lookahead"] = advice["lookahead"]
    if advice.get("exact_line"):
        out["exact_line"] = advice["exact_line"]
    if advice.get("exact_1v1"):
        out["exact_1v1"] = True
        out["outcome"] = advice.get("outcome")
    return out


def completed_payload(session) -> dict[str, Any]:
    """Analysis-first JSON for games/completed/…"""
    g = session.game
    names = [p.name for p in g.players]
    review = getattr(session, "review", None) or new_review(session.mode, names)

    winners = []
    for place, p in enumerate(g.winners, start=1):
        seat = next(i for i, pl in enumerate(g.players) if pl is p)
        winners.append({"place": place, "seat": seat, "name": p.name})

    leftover = g.remaining_players()
    loser = None
    if leftover:
        lp = leftover[0]
        seat = next(i for i, pl in enumerate(g.players) if pl is lp)
        loser = {"seat": seat, "name": lp.name}

    return {
        "version": 2,
        "id": session.id,
        "mode": session.mode,
        "players": names,
        "result": {
            "finishing_order": winners,
            "loser": loser,
        },
        "opening_hands": review.get("opening_hands"),
        "tricks": review.get("tricks") or [],
        "takes": review.get("takes") or [],
        "advice_requests": review.get("advice_requests") or [],
    }


def completed_markdown(payload: dict[str, Any]) -> str:
    """Human-scannable companion next to the completed JSON."""
    mode = "Human vs AI" if payload.get("mode") == "human" else "AI vs AI"
    lines = [
        f"# Game `{payload.get('id', '?')}`",
        "",
        f"**Mode:** {mode}",
        "",
    ]

    result = payload.get("result") or {}
    order = result.get("finishing_order") or []
    loser = result.get("loser")
    if order or loser:
        bits = [f"{w['place']}. {w['name']}" for w in order]
        if loser:
            bits.append(f"Last: {loser['name']}")
        lines.append("**Result:** " + " · ".join(bits))
        lines.append("")

    opening = payload.get("opening_hands")
    if opening:
        lines.append("## Opening hands")
        lines.append("")
        players = payload.get("players") or []
        for i, hand in enumerate(opening):
            name = players[i] if i < len(players) else f"Seat {i}"
            cards = " ".join(hand) if hand else "(empty)"
            lines.append(f"- **{name}:** {cards}")
        lines.append("")

    for trick in payload.get("tricks") or []:
        n = trick.get("n")
        lead = trick.get("leader")
        first = " · first trick (AS)" if trick.get("first_trick") else ""
        lines.append(f"## Trick {n} — lead {lead}{first}")
        lines.append("")
        for play in trick.get("plays") or []:
            lines.append(_format_play_line(play))
        result_s = trick.get("result")
        if result_s == "thulla":
            lines.append(
                f"- **THULLA** → {trick.get('victim')} picks up "
                f"{' '.join(trick.get('pot') or [])}"
            )
        elif result_s == "win":
            lines.append(
                f"- **Won by {trick.get('winner')}** · discarded "
                f"{' '.join(trick.get('pot') or [])}"
            )
        lines.append("")

    takes = payload.get("takes") or []
    if takes:
        lines.append("## Takes")
        lines.append("")
        for t in takes:
            lines.append(_format_take_line(t))
        lines.append("")

    advice_reqs = payload.get("advice_requests") or []
    if advice_reqs:
        lines.append("## Ideal Move requests")
        lines.append("")
        for a in advice_reqs:
            lines.append(_format_advice_request(a))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _format_play_line(play: dict[str, Any]) -> str:
    name = play.get("name", "?")
    card = play.get("card", "?")
    kind = play.get("kind", "play")
    hand = " ".join(play.get("hand_before") or [])
    legal = " ".join(play.get("legal") or [])
    bits = [f"- **{name}** plays `{card}` ({kind})"]
    if play.get("lead_suit"):
        bits[0] += f" · led {play['lead_suit']}"
    if play.get("current_highest"):
        bits[0] += f" · high {play['current_highest']}"
    extra = []
    if hand:
        extra.append(f"  - hand: {hand}")
    if legal:
        extra.append(f"  - legal: {legal}")
    adv = play.get("advice")
    if adv and adv.get("recommended"):
        rec = adv["recommended"]
        if isinstance(rec, dict) and rec.get("card"):
            rec_s = rec["card"]
        elif isinstance(rec, dict) and "accept" in rec:
            rec_s = "ask" if rec["accept"] else "decline"
        else:
            rec_s = str(rec)
        followed = play.get("followed_advice")
        flag = ""
        if followed is True:
            flag = " ✓ matched Ideal"
        elif followed is False:
            flag = " ✗ differed from Ideal"
        extra.append(f"  - Ideal: `{rec_s}`{flag}")
        for step in adv.get("steps") or []:
            label = step.get("label", "")
            detail = step.get("detail", "")
            extra.append(f"    - {label}: {detail}")
        # Prefer showing exact line even if truncated above missed it.
        if adv.get("exact_line") and not any(
            (s.get("label") or "") == "LINE" for s in (adv.get("steps") or [])
        ):
            parts = []
            for step in adv["exact_line"]:
                if not step.get("card"):
                    parts.append(step.get("note") or "")
                else:
                    who = "You" if step.get("side") == "you" else "Opp"
                    note = step.get("note") or ""
                    parts.append(
                        f"{who} {step['card']}" + (f" ({note})" if note else "")
                    )
            extra.append(f"    - LINE: {' → '.join(parts)}")
    return "\n".join(bits + extra)


def _format_take_line(t: dict[str, Any]) -> str:
    after = t.get("after_trick")
    prefix = f"T{after}: " if after is not None else ""
    if t.get("given"):
        line = (
            f"- {prefix}**{t.get('asker')}** takes "
            f"**{t.get('target')}**'s {t.get('n_cards')} cards"
        )
    else:
        line = (
            f"- {prefix}**{t.get('target')}** refuses **{t.get('asker')}**"
        )
    adv = t.get("advice")
    if adv and adv.get("recommended"):
        rec = adv["recommended"]
        if isinstance(rec, dict) and "accept" in rec:
            rec_s = "yes" if rec["accept"] else "no"
            followed = t.get("followed_advice")
            flag = " ✓" if followed else (" ✗" if followed is False else "")
            line += f" · Ideal: {rec_s}{flag}"
    return line


def _format_advice_request(a: dict[str, Any]) -> str:
    trick = a.get("trick_number")
    phase = a.get("phase")
    adv = a.get("advice") or {}
    rec = adv.get("recommended")
    if isinstance(rec, dict) and rec.get("card"):
        rec_s = rec["card"]
    elif isinstance(rec, dict) and "accept" in rec:
        rec_s = "ask" if rec["accept"] else "decline"
    else:
        rec_s = "—"
    return f"- Trick {trick} ({phase}): Ideal → `{rec_s}` ({adv.get('kind') or adv.get('action')})"
