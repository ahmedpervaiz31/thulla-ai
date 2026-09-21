"""Replay completed-game JSON into UI frames for turn scrubbing."""

from __future__ import annotations

from typing import Any

from .cards import Card, parse_card
from .session import GameSession


def load_review_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Build a review response by replaying opening hands + tricks + takes."""
    try:
        frames = rebuild_frames_from_review(data)
    except (RuntimeError, ValueError, KeyError, TypeError):
        frames = []
    return {
        "id": data.get("id"),
        "mode": data.get("mode"),
        "players": data.get("players") or [],
        "result": data.get("result"),
        "saved_at": data.get("saved_at"),
        "frame_count": len(frames),
        "frames": frames,
    }


def frames_from_session(session: GameSession) -> list[dict[str, Any]]:
    """Replay the in-memory review log (same path as completed JSON)."""
    review = getattr(session, "review", None) or {}
    return rebuild_frames_from_review(
        {
            "id": session.id,
            "mode": session.mode,
            "players": [p.name for p in session.game.players],
            "opening_hands": review.get("opening_hands"),
            "tricks": review.get("tricks") or [],
            "takes": review.get("takes") or [],
        }
    )


def rebuild_frames_from_review(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Replay opening hands + logged tricks/takes into UI frames with seat hands."""
    opening = payload.get("opening_hands")
    players = payload.get("players") or []
    mode = payload.get("mode") or "human"
    if not opening or not players:
        return []

    n = len(players)
    session = GameSession(mode, n, game_id=payload.get("id"), deal=False)
    for i, name in enumerate(players):
        if i < len(session.game.players):
            session.game.players[i].name = name

    hands: list[list[Card]] = []
    ace_idx = 0
    for i, codes in enumerate(opening):
        cards = []
        for code in codes:
            card = parse_card(code)
            if card is None:
                raise ValueError(f"bad opening card: {code}")
            if card.code() == "AS":
                ace_idx = i
            cards.append(card)
        hands.append(cards)

    session.game.set_hands(hands, ace_spades_holder_idx=ace_idx)
    session.review = {
        "mode": mode,
        "players": list(players),
        "opening_hands": [list(h) for h in opening],
        "tricks": [],
        "takes": [],
        "advice_requests": [],
    }
    session.leader = ace_idx
    frames: list[dict[str, Any]] = []
    session._start_trick(first_trick=True)
    frames.append(session.to_dict(reveal_hands=True))

    takes = list(payload.get("takes") or [])
    take_i = 0
    tricks = payload.get("tricks") or []

    for trick in tricks:
        for play in trick.get("plays") or []:
            _replay_until_play(session)
            card = play.get("card")
            if not card:
                raise ValueError("review play missing card")
            _force_play(session, card)
            frames.append(session.to_dict(reveal_hands=True))

        if session.phase == "trick_reveal":
            frames.append(session.to_dict(reveal_hands=True))
            session.step()
            frames.append(session.to_dict(reveal_hands=True))

        after_n = trick.get("n")
        while take_i < len(takes) and takes[take_i].get("after_trick") == after_n:
            entry = takes[take_i]
            take_i += 1
            _replay_take_entry(session, entry)
            frames.append(session.to_dict(reveal_hands=True))

    guard = 0
    while session.phase != "finished" and guard < 50:
        if session.pending and session.pending.get("type") == "reveal":
            session.step()
            frames.append(session.to_dict(reveal_hands=True))
        else:
            break
        guard += 1

    if session.phase != "finished" and len(session.game.active_player_indices) <= 1:
        session._finish_game()
        frames.append(session.to_dict(reveal_hands=True))

    return frames


def _replay_until_play(session: GameSession) -> None:
    guard = 0
    while session.phase != "finished" and guard < 100:
        pending = session.pending
        if pending and pending.get("type") == "play":
            return
        if pending and pending.get("type") == "reveal":
            session.step()
        else:
            break
        guard += 1
    if not session.pending or session.pending.get("type") != "play":
        raise RuntimeError("expected play pending while rebuilding review")


def _force_play(session: GameSession, card_code: str) -> None:
    if not session.pending or session.pending.get("type") != "play":
        raise RuntimeError("not awaiting a card play for review rebuild")
    seat = session.pending["seat"]
    card = parse_card(card_code)
    if card is None:
        raise ValueError(f"invalid card code: {card_code}")
    assert session.trick is not None
    hand_before = [c.code() for c in session.game.players[seat].hand]
    legal = list(session.pending.get("legal") or [])
    session._log_play(seat, card, hand_before=hand_before, legal=legal)
    result = session.game.apply_play(session.trick, seat, card)
    if result != "continue":
        session._enter_trick_reveal()
    else:
        session._set_play_pending_or_none()


def _replay_take_entry(session: GameSession, entry: dict[str, Any]) -> None:
    """Apply one logged take resolution without re-rolling CPU decisions."""
    guard = 0
    while session.phase == "take" and guard < 40:
        pending = session.pending
        if not pending:
            session._set_take_pending_or_advance()
            guard += 1
            continue
        if pending.get("type") == "take":
            asker = entry.get("asker_seat", pending["seat"])
            if pending["seat"] != asker:
                raise RuntimeError(
                    f"take asker mismatch: pending {pending['seat']} vs log {asker}"
                )
            given = bool(entry.get("given"))
            decision = entry.get("human_decision")
            if not given and decision != "refuse":
                session._resolve_take_ask(pending["seat"], False)
            else:
                session._complete_take(pending["seat"], pending["target"], given)
            return
        if pending.get("type") == "give":
            session._resolve_give(pending["seat"], bool(entry.get("given")))
            return
        break
