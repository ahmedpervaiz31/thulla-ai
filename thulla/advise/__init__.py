"""Structured move advice using the same policy as ComputerPlayer."""

from __future__ import annotations

from typing import Any

from .play import _exact_advice, advise_play
from .take import advise_give, advise_take


def advise_pending(session) -> dict[str, Any]:
    """Bot-policy advice for whoever currently has a play / take / give pending."""
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

    if pending["type"] == "play":
        return advise_play(session)
    if pending["type"] == "take":
        return advise_take(session)
    if pending["type"] == "give":
        return advise_give(session)

    return {"available": False, "reason": f"No advice for pending {pending['type']}."}


def advise_session(session) -> dict[str, Any]:
    """Return bot-policy advice for the human seat (human mode coach only)."""
    if session.mode != "human":
        return {
            "available": False,
            "reason": "Ideal move is only available in human vs AI.",
        }

    pending = session.pending
    if pending is not None and pending["type"] in ("play", "take", "give"):
        seat = pending.get("seat")
        if seat is None or not session.is_human(seat):
            return {
                "available": False,
                "phase": session.phase,
                "reason": "Not your turn — waiting on a CPU.",
                "whose_turn": seat,
            }

    return advise_pending(session)


__all__ = ["advise_session", "advise_pending", "_exact_advice"]
