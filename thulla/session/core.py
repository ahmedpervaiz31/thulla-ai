"""GameSession shell: construction, finish, advice wiring, session store."""

from __future__ import annotations

import uuid
from typing import Any

from ..game import ThullaGame, TrickState
from ..players import ComputerPlayer
from ..review import compact_advice, new_review
from .advance import AdvanceMixin
from .seats import InteractiveSeat
from .serialize import SerializeMixin
from .take import TakeMixin
from .trick import TrickMixin


def _make_cpu(name: str, player_count: int):
    """Prefer DMC (model_best) for 4-player tables; else heuristic ComputerPlayer."""
    try:
        from thulla_dmc.player import DMCPlayer, make_app_bot

        bot = make_app_bot(name, player_count)
        if isinstance(bot, DMCPlayer):
            if name.startswith("CPU"):
                bot.name = name.replace("CPU", "DMC", 1)
        elif name.startswith("DMC"):
            # Checkpoint missing after resume — keep policy label honest.
            bot.name = name.replace("DMC", "CPU", 1)
        return bot
    except ImportError:
        return ComputerPlayer(
            name.replace("DMC", "CPU", 1) if name.startswith("DMC") else name
        )


def _bind_dmc_bots(session: "GameSession"):
    """Share one play-history list across all DMC seats."""
    try:
        from thulla_dmc.player import DMCPlayer
    except ImportError:
        session.bot_kind = "heuristic"
        return
    history = getattr(session, "dmc_play_history", None)
    if history is None:
        history = []
        session.dmc_play_history = history
    any_dmc = False
    for p in session.game.players:
        if isinstance(p, DMCPlayer):
            p.bind(session.game, history)
            any_dmc = True
    session.bot_kind = "dmc" if any_dmc else "heuristic"


class GameSession(TrickMixin, TakeMixin, AdvanceMixin, SerializeMixin):
    """
    Drives Thulla one decision at a time.

    Phases: first_trick | take | trick | finished
    """

    def __init__(
        self,
        mode: str,
        player_count: int,
        game_id: str | None = None,
        *,
        deal: bool = True,
    ):
        if mode not in ("human", "ai"):
            raise ValueError("mode must be 'human' or 'ai'")
        if player_count < 3 or player_count > 8:
            raise ValueError("player count must be between 3 and 8")

        self.id = game_id or str(uuid.uuid4())
        self.mode = mode
        self.human_seat = 0 if mode == "human" else None
        self.dmc_play_history: list = []
        self.bot_kind = "heuristic"

        if mode == "human":
            players = [InteractiveSeat("You")]
            for i in range(1, player_count):
                players.append(_make_cpu(f"CPU{i}", player_count))
        else:
            players = [
                _make_cpu(f"CPU{i}", player_count) for i in range(1, player_count + 1)
            ]

        self.game = ThullaGame(players, verbose=False)
        _bind_dmc_bots(self)
        self.phase = "first_trick"
        self.leader: int | None = None
        self.trick: TrickState | None = None
        self.take_queue: list[int] = []
        self.take_leader: int | None = None
        self.pending: dict[str, Any] | None = None
        self.last_event: str | None = None
        self.status = "Starting"
        self.review: dict[str, Any] = new_review(mode, [p.name for p in players])
        self._review_trick: dict[str, Any] | None = None
        self.last_advice: dict[str, Any] | None = None

        if deal:
            self.game.shuffle_and_deal()
            self.review["opening_hands"] = [
                [c.code() for c in p.hand] for p in self.game.players
            ]
            self.leader = self.game.ace_spades_holder_idx
            self._start_trick(first_trick=True)
        # Client paces CPU plays via /step (see trick_reveal for readable pot).

    def is_human(self, seat: int) -> bool:
        return self.human_seat is not None and seat == self.human_seat

    def _snapshot_advice_for_pending(self) -> dict[str, Any] | None:
        """Ideal Move / bot-policy reasoning for the seat that must decide now."""
        if self.pending is None:
            return None
        if self.pending.get("type") not in ("play", "take", "give"):
            return None
        from ..advise import advise_pending

        return compact_advice(advise_pending(self))

    def record_advice_request(self, advice: dict[str, Any]):
        """Persist an Ideal Move fetch (human mode coach panel)."""
        compact = compact_advice(advice)
        self.last_advice = compact
        if compact is None:
            return
        self.review.setdefault("advice_requests", []).append(
            {
                "trick_number": self.game.trick_number,
                "phase": self.phase,
                "pending": (self.pending or {}).get("type"),
                "advice": compact,
            }
        )

    def _finish_game(self):
        self.phase = "finished"
        self.pending = None
        self.trick = None
        self.status = "Game over"
        self.last_event = "Game over"


# In-memory store for the web app
SESSIONS: dict[str, GameSession] = {}


def create_session(mode: str, players: int) -> GameSession:
    session = GameSession(mode, players)
    SESSIONS[session.id] = session
    return session


def get_session(game_id: str) -> GameSession | None:
    """In-memory lookup only. Prefer thulla.persist.get_or_load_session for API."""
    return SESSIONS.get(game_id)
