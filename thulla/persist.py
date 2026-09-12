"""Disk persistence for web game sessions + analysis logs."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .cards import Card, parse_card
from .game import TrickState
from .info import PublicInfo
from .players import ComputerPlayer
from .session import GameSession, InteractiveSeat, SESSIONS

# Repo root / games / {human_vs_ai|ai_vs_ai} / {game_id}.json
GAMES_ROOT = Path(__file__).resolve().parent.parent / "games"
MODE_DIRS = {
    "human": "human_vs_ai",
    "ai": "ai_vs_ai",
}


def mode_dir(mode: str) -> Path:
    name = MODE_DIRS.get(mode, mode)
    path = GAMES_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def game_path(mode: str, game_id: str) -> Path:
    return mode_dir(mode) / f"{game_id}.json"


def _card_code(card: Card | None) -> str | None:
    return card.code() if card is not None else None


def _parse_codes(codes: list[str] | None) -> list[Card]:
    out = []
    for code in codes or []:
        card = parse_card(code)
        if card is None:
            raise ValueError(f"bad card code in checkpoint: {code}")
        out.append(card)
    return out


def info_to_dict(info: PublicInfo) -> dict[str, Any]:
    return {
        "player_cnt": info.player_cnt,
        "active_indices": list(info.active_indices),
        "discarded": sorted(c.code() for c in info.discarded),
        "known_holdings": {
            str(i): sorted(c.code() for c in cards)
            for i, cards in info.known_holdings.items()
        },
        "voids": {
            str(i): sorted(suits) for i, suits in info.voids.items()
        },
        "hand_sizes": list(info.hand_sizes),
        "led_suit": info.led_suit,
        "current_highest": _card_code(info.current_highest),
        "current_highest_player": info.current_highest_player,
        "trick_cards": [c.code() for c in info.trick_cards],
        "played_by": {
            str(i): [c.code() for c in cards]
            for i, cards in info.played_by.items()
        },
        "highest_played": {
            str(i): {suit: card.code() for suit, card in suits.items()}
            for i, suits in info.highest_played.items()
        },
        "suit_high_shown": {
            str(i): {suit: card.code() for suit, card in suits.items()}
            for i, suits in info.suit_high_shown.items()
        },
        "under_ceilings": {
            str(i): {
                suit: {"played": lo.code(), "ceiling": hi.code()}
                for suit, (lo, hi) in ceilings.items()
            }
            for i, ceilings in info.under_ceilings.items()
        },
    }


def info_from_dict(data: dict[str, Any]) -> PublicInfo:
    info = PublicInfo(data["player_cnt"])
    info.active_indices = list(data.get("active_indices", list(range(info.player_cnt))))
    info.discarded = set(_parse_codes(data.get("discarded")))
    info.known_holdings = {
        int(k): set(_parse_codes(v)) for k, v in data.get("known_holdings", {}).items()
    }
    for i in range(info.player_cnt):
        info.known_holdings.setdefault(i, set())
    info.voids = {
        int(k): set(v) for k, v in data.get("voids", {}).items()
    }
    for i in range(info.player_cnt):
        info.voids.setdefault(i, set())
    info.hand_sizes = list(data.get("hand_sizes", [0] * info.player_cnt))
    info.led_suit = data.get("led_suit")
    hi = data.get("current_highest")
    info.current_highest = parse_card(hi) if hi else None
    info.current_highest_player = data.get("current_highest_player")
    info.trick_cards = _parse_codes(data.get("trick_cards"))
    info.played_by = {
        int(k): _parse_codes(v) for k, v in data.get("played_by", {}).items()
    }
    for i in range(info.player_cnt):
        info.played_by.setdefault(i, [])
    info.highest_played = {
        int(k): {suit: parse_card(code) for suit, code in suits.items()}
        for k, suits in data.get("highest_played", {}).items()
    }
    for i in range(info.player_cnt):
        info.highest_played.setdefault(i, {})
    info.suit_high_shown = {
        int(k): {suit: parse_card(code) for suit, code in suits.items()}
        for k, suits in data.get("suit_high_shown", {}).items()
    }
    for i in range(info.player_cnt):
        info.suit_high_shown.setdefault(i, {})
    info.under_ceilings = {}
    for k, ceilings in data.get("under_ceilings", {}).items():
        idx = int(k)
        info.under_ceilings[idx] = {}
        for suit, pair in ceilings.items():
            lo = parse_card(pair["played"])
            hi_c = parse_card(pair["ceiling"])
            if lo and hi_c:
                info.under_ceilings[idx][suit] = (lo, hi_c)
    for i in range(info.player_cnt):
        info.under_ceilings.setdefault(i, {})
    return info


def trick_to_dict(trick: TrickState | None) -> dict[str, Any] | None:
    if trick is None:
        return None
    return {
        "leader_idx": trick.leader_idx,
        "first_trick": trick.first_trick,
        "order": list(trick.order),
        "colour": trick.colour,
        "stack": [c.code() for c in trick.stack],
        "highest_card": _card_code(trick.highest_card),
        "highest_idx": trick.highest_idx,
        "plays": [{"player": name, "card": card.code()} for name, card in trick.plays],
        "seat_pos": trick.seat_pos,
        "done": trick.done,
        "result": trick.result,
        "next_leader": trick.next_leader,
    }


def trick_from_dict(data: dict[str, Any] | None) -> TrickState | None:
    if not data:
        return None
    plays = []
    for entry in data.get("plays", []):
        card = parse_card(entry["card"])
        if card is None:
            raise ValueError(f"bad trick play: {entry}")
        plays.append((entry["player"], card))
    hi = data.get("highest_card")
    return TrickState(
        leader_idx=data["leader_idx"],
        first_trick=data["first_trick"],
        order=list(data["order"]),
        colour=data.get("colour"),
        stack=_parse_codes(data.get("stack")),
        highest_card=parse_card(hi) if hi else None,
        highest_idx=data.get("highest_idx"),
        plays=plays,
        seat_pos=data.get("seat_pos", 0),
        done=bool(data.get("done")),
        result=data.get("result"),
        next_leader=data.get("next_leader"),
    )


def session_checkpoint(session: GameSession) -> dict[str, Any]:
    g = session.game
    winners = []
    for p in g.winners:
        for i, pl in enumerate(g.players):
            if pl is p:
                winners.append(i)
                break

    return {
        "version": 1,
        "saved_at": time.time(),
        "id": session.id,
        "mode": session.mode,
        "phase": session.phase,
        "status": session.status,
        "last_event": session.last_event,
        "leader": session.leader,
        "take_queue": list(session.take_queue),
        "take_leader": session.take_leader,
        "pending": session.pending,
        "reveal_was_first": getattr(session, "_reveal_was_first", None),
        "reveal_next_leader": getattr(session, "_reveal_next_leader", None),
        "trick": trick_to_dict(session.trick),
        "game": {
            "player_count": g.player_cnt,
            "ace_spades_holder_idx": g.ace_spades_holder_idx,
            "trick_number": g.trick_number,
            "active_player_indices": list(g.active_player_indices),
            "winners": winners,
            "hands": [[c.code() for c in p.hand] for p in g.players],
            "names": [p.name for p in g.players],
            "info": info_to_dict(g.info),
        },
        "client": session.to_dict(),
        "events": list(getattr(session, "event_log", [])),
    }


def save_session(session: GameSession) -> Path:
    path = game_path(session.mode, session.id)
    payload = session_checkpoint(session)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_checkpoint(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_checkpoint(game_id: str) -> Path | None:
    for folder in MODE_DIRS.values():
        path = GAMES_ROOT / folder / f"{game_id}.json"
        if path.is_file():
            return path
    return None


def session_from_checkpoint(data: dict[str, Any]) -> GameSession:
    mode = data["mode"]
    gdata = data["game"]
    n = gdata["player_count"]
    session = GameSession(mode, n, game_id=data["id"], deal=False)

    # Rebuild seats with saved names
    names = gdata.get("names") or []
    if mode == "human":
        players = [InteractiveSeat(names[0] if names else "You")]
        for i in range(1, n):
            name = names[i] if i < len(names) else f"CPU{i}"
            players.append(ComputerPlayer(name))
    else:
        players = [
            ComputerPlayer(names[i] if i < len(names) else f"CPU{i + 1}")
            for i in range(n)
        ]
    session.game.players = players

    hands = [_parse_codes(h) for h in gdata["hands"]]
    for p, hand in zip(players, hands):
        p.hand = list(hand)
        p.sort_hand()

    session.game.ace_spades_holder_idx = gdata.get("ace_spades_holder_idx", 0)
    session.game.trick_number = gdata.get("trick_number", 0)
    session.game.active_player_indices = list(
        gdata.get("active_player_indices", list(range(n)))
    )
    session.game.winners = [
        players[i] for i in gdata.get("winners", []) if 0 <= i < n
    ]
    session.game.info = info_from_dict(gdata["info"])

    session.phase = data["phase"]
    session.status = data.get("status", "")
    session.last_event = data.get("last_event")
    session.leader = data.get("leader")
    session.take_queue = list(data.get("take_queue") or [])
    session.take_leader = data.get("take_leader")
    session.pending = data.get("pending")
    session.trick = trick_from_dict(data.get("trick"))
    if data.get("reveal_was_first") is not None:
        session._reveal_was_first = data["reveal_was_first"]
    if data.get("reveal_next_leader") is not None:
        session._reveal_next_leader = data["reveal_next_leader"]
    session.event_log = list(data.get("events") or [])
    return session


def persist_and_return(session: GameSession) -> dict:
    """Save checkpoint then return client-facing state."""
    append_event(session, "state", session.to_dict())
    try:
        save_session(session)
    except OSError:
        # Disk failures should not break play.
        pass
    return session.to_dict()


def append_event(session: GameSession, kind: str, payload: dict | None = None):
    if not hasattr(session, "event_log"):
        session.event_log = []
    entry = {"t": time.time(), "kind": kind}
    if payload is not None:
        # Keep log compact: status/phase/trick only for routine snapshots.
        if kind == "state":
            entry["phase"] = payload.get("phase")
            entry["status"] = payload.get("status")
            entry["trick_number"] = payload.get("trick_number")
            entry["whose_turn"] = payload.get("whose_turn")
            if payload.get("last_event"):
                entry["last_event"] = payload["last_event"]
            if payload.get("finished"):
                entry["finished"] = True
                entry["winners"] = payload.get("winners")
                entry["loser"] = payload.get("loser")
        else:
            entry["payload"] = payload
    session.event_log.append(entry)


def get_or_load_session(game_id: str) -> GameSession | None:
    session = SESSIONS.get(game_id)
    if session is not None:
        return session
    path = find_checkpoint(game_id)
    if path is None:
        return None
    try:
        data = load_checkpoint(path)
        session = session_from_checkpoint(data)
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None
    SESSIONS[session.id] = session
    return session
