"""Disk persistence for web game sessions + analysis logs."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from .cards import Card, parse_card
from .game import TrickState
from .info import PublicInfo
from .players import ComputerPlayer
from .review import completed_markdown, completed_payload, new_review
from .session import GameSession, InteractiveSeat, SESSIONS

# games/ongoing|completed/{human_vs_ai|ai_vs_ai}/{game_id}.json
GAMES_ROOT = Path(__file__).resolve().parent.parent / "games"
MODE_DIRS = {
    "human": "human_vs_ai",
    "ai": "ai_vs_ai",
}
BUCKETS = ("ongoing", "completed")


def mode_name(mode: str) -> str:
    return MODE_DIRS.get(mode, mode)


def mode_dir(mode: str, bucket: str = "ongoing") -> Path:
    path = GAMES_ROOT / bucket / mode_name(mode)
    path.mkdir(parents=True, exist_ok=True)
    return path


def game_path(mode: str, game_id: str, bucket: str = "ongoing") -> Path:
    return mode_dir(mode, bucket) / f"{game_id}.json"


def completed_md_path(mode: str, game_id: str) -> Path:
    return mode_dir(mode, "completed") / f"{game_id}.md"


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
        "thulla_by": trick.thulla_by,
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
        thulla_by=data.get("thulla_by"),
    )


def session_checkpoint(session: GameSession) -> dict[str, Any]:
    """Full resume checkpoint for games/ongoing/…"""
    g = session.game
    winners = []
    for p in g.winners:
        for i, pl in enumerate(g.players):
            if pl is p:
                winners.append(i)
                break

    return {
        "version": 2,
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
        "review": getattr(session, "review", None),
        "last_advice": getattr(session, "last_advice", None),
        "review_trick": getattr(session, "_review_trick", None),
    }


def save_session(session: GameSession) -> Path:
    """Write ongoing checkpoint (resume). Finished games also get a completed export."""
    ensure_games_layout()
    path = game_path(session.mode, session.id, bucket="ongoing")
    payload = session_checkpoint(session)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if session.phase == "finished":
        write_completed(session)
        # Finished games stay loadable from completed/; drop ongoing copy.
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return game_path(session.mode, session.id, bucket="completed")
    return path


def write_completed(session: GameSession) -> Path:
    """Analysis-first JSON + markdown under games/completed/…"""
    ensure_games_layout()
    payload = completed_payload(session)
    payload["saved_at"] = time.time()
    path = game_path(session.mode, session.id, bucket="completed")
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = completed_md_path(session.mode, session.id)
    md.write_text(completed_markdown(payload), encoding="utf-8")
    return path


def load_checkpoint(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_checkpoint(game_id: str) -> Path | None:
    """Prefer ongoing resume files, then completed, then legacy flat folders."""
    for bucket in ("ongoing", "completed"):
        for folder in MODE_DIRS.values():
            path = GAMES_ROOT / bucket / folder / f"{game_id}.json"
            if path.is_file():
                return path
    # Legacy: games/{mode}/{id}.json
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

    review = data.get("review")
    if review:
        session.review = review
    else:
        session.review = new_review(mode, names or [p.name for p in players])
    session._review_trick = data.get("review_trick")
    session.last_advice = data.get("last_advice")
    # Legacy noisy event log (ignored going forward).
    session.event_log = list(data.get("events") or [])
    return session


def persist_and_return(session: GameSession) -> dict:
    """Save checkpoint then return client-facing state."""
    try:
        save_session(session)
    except OSError:
        # Disk failures should not break play.
        pass
    return session.to_dict()


def get_or_load_session(game_id: str) -> GameSession | None:
    session = SESSIONS.get(game_id)
    if session is not None:
        return session
    path = find_checkpoint(game_id)
    if path is None:
        return None
    try:
        data = load_checkpoint(path)
        # Completed analysis files (version 2 without full game blob) are not resumable.
        if "game" not in data:
            return None
        session = session_from_checkpoint(data)
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None
    SESSIONS[session.id] = session
    return session


def ensure_games_layout() -> None:
    for bucket in BUCKETS:
        for folder in MODE_DIRS.values():
            (GAMES_ROOT / bucket / folder).mkdir(parents=True, exist_ok=True)


def migrate_legacy_games() -> dict[str, int]:
    """Move flat games/{mode}/*.json into ongoing/ or completed/."""
    ensure_games_layout()
    moved = {"ongoing": 0, "completed": 0, "skipped": 0}
    for folder in MODE_DIRS.values():
        legacy = GAMES_ROOT / folder
        if not legacy.is_dir():
            continue
        for path in legacy.glob("*.json"):
            try:
                data = load_checkpoint(path)
            except (OSError, json.JSONDecodeError):
                moved["skipped"] += 1
                continue
            mode = data.get("mode")
            if mode not in MODE_DIRS:
                # Infer from folder
                mode = "human" if folder == "human_vs_ai" else "ai"
            gid = data.get("id") or path.stem
            finished = data.get("phase") == "finished" or bool(
                (data.get("client") or {}).get("finished")
            )
            bucket = "completed" if finished else "ongoing"
            dest = game_path(mode, gid, bucket=bucket)
            if dest.exists():
                moved["skipped"] += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            if bucket == "completed" and "game" in data:
                # Re-export analysis format when we still have a full checkpoint.
                try:
                    session = session_from_checkpoint(data)
                    write_completed(session)
                    path.unlink(missing_ok=True)
                    moved["completed"] += 1
                    continue
                except (KeyError, ValueError, TypeError):
                    pass
            shutil.move(str(path), str(dest))
            moved[bucket] += 1
    return moved
