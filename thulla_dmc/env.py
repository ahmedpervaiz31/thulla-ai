"""Gym-style Thulla environment for DMC self-play (fixed 4 seats)."""

from __future__ import annotations

from typing import Any

import numpy as np

from thulla.cards import Card, valid_moves
from thulla.game import ThullaGame
from thulla.players import BasePlayer

from .encode import (
    ASK,
    PASS,
    NUM_PLAYERS,
    Action,
    build_action_batch,
    encode_action,
    encode_state,
)

# Finish-rank rewards for 4 players (1st away … last).
FINISH_REWARDS = (1.2, 1.1, 1.0, -1.0)


class DummySeat(BasePlayer):
    """Seat controlled by the env — never chooses via play_turn; give always yes."""

    def play_turn(self, expected_cards, view=None):
        raise RuntimeError("DummySeat must not play_turn; env selects cards")

    def offer_take(self, target_name, n_cards, view=None, neighbor_idx=None, i_am_leader=False):
        raise RuntimeError("DummySeat take is decided by the env")

    def offer_give(self, asker_name, n_cards, view=None, asker_idx=None):
        return True


class ThullaEnv:
    """
    Step-based wrapper around ThullaGame.

    Card plays and take-phase ASK/PASS are both learned. Victims always give.
    Terminal rewards use FINISH_REWARDS by finish order.
    """

    def __init__(self, num_players: int = NUM_PLAYERS):
        if num_players != NUM_PLAYERS:
            raise ValueError(f"MVP supports exactly {NUM_PLAYERS} players")
        self.num_players = num_players
        self.game: ThullaGame | None = None
        self.trick = None
        self.leader: int | None = None
        self.play_history: list[Card] = []
        self._seat_returns: dict[int, float] = {}
        self.phase: str = "play"  # "play" | "take"
        self._take_queue: list[int] = []
        self._take_pos: int = 0
        self._take_leader: int | None = None

    def reset(self) -> dict[str, Any]:
        players = [DummySeat(f"P{i}") for i in range(self.num_players)]
        self.game = ThullaGame(players, verbose=False)
        self.game.shuffle_and_deal()
        self.play_history = []
        self._seat_returns = {}
        self.phase = "play"
        self._take_queue = []
        self._take_pos = 0
        self._take_leader = None
        self.leader = self.game.ace_spades_holder_idx
        self.trick = self.game.begin_trick(self.leader, first_trick=True)
        if self.trick is None:
            raise RuntimeError("failed to start first trick")
        return self._obs_for_current()

    @property
    def current_seat(self) -> int:
        if self.phase == "take":
            return self._take_queue[self._take_pos]
        assert self.trick is not None
        return self.trick.order[self.trick.seat_pos]

    def legal_actions(self) -> list[Action]:
        assert self.game is not None
        if self.phase == "take":
            return [ASK, PASS]
        assert self.trick is not None
        seat = self.current_seat
        expected = self.game.expected_for_seat(self.trick, seat)
        return valid_moves(self.game.players[seat].hand, expected)

    def _obs_for_current(self) -> dict[str, Any]:
        assert self.game is not None
        seat = self.current_seat
        legal = self.legal_actions()
        take = self.phase == "take"
        i_am_leader = bool(take and seat == self._take_leader)
        trick = None if take else self.trick
        x_no, z = encode_state(
            self.game,
            seat,
            trick,
            self.play_history,
            take_phase=take,
            i_am_leader=i_am_leader,
        )
        x_batch, z_batch = build_action_batch(x_no, z, legal)
        return {
            "position": seat,
            "legal_actions": legal,
            "x_no_action": x_no,
            "z": z,
            "x_batch": x_batch,
            "z_batch": z_batch,
            "phase": self.phase,
        }

    def step(self, action: Action) -> tuple[dict[str, Any] | None, np.ndarray, bool, dict]:
        """
        Apply one action (card or ASK/PASS).

        Returns (obs, rewards_per_seat, done, info).
        rewards_per_seat is shape (4,) — zeros until terminal, then finish rewards.
        """
        if self.phase == "take":
            return self._step_take(action)
        return self._step_play(action)

    def _step_play(self, action: Action):
        assert self.game is not None and self.trick is not None
        if not isinstance(action, Card):
            raise ValueError(f"expected card during play phase, got {action!r}")
        seat = self.current_seat
        legal = self.legal_actions()
        if action not in legal:
            raise ValueError(f"illegal action {action}; legal={legal}")

        self.game.apply_play(self.trick, seat, action)
        self.play_history.append(action)

        rewards = np.zeros(self.num_players, dtype=np.float32)
        info: dict[str, Any] = {"seat": seat, "action": action, "phase": "play"}

        if not self.trick.done:
            return self._obs_for_current(), rewards, False, info

        next_leader = self.trick.next_leader
        next_leader = self.game.check_got_away(next_leader)

        if self._is_finished(next_leader):
            return self._terminal(seat, action)

        return self._begin_take_phase(next_leader, seat, action)

    def _step_take(self, action: Action):
        assert self.game is not None and self._take_leader is not None
        if action not in (ASK, PASS):
            raise ValueError(f"expected ASK/PASS during take phase, got {action!r}")

        seat = self.current_seat
        accept = action == ASK
        # Victim always gives when asked (DummySeat.offer_give).
        self.leader = self.game.apply_take(self._take_leader, seat, accept)

        rewards = np.zeros(self.num_players, dtype=np.float32)
        info: dict[str, Any] = {"seat": seat, "action": action, "phase": "take"}

        if self._is_finished(self.leader):
            return self._terminal(seat, action)

        self._take_pos += 1
        self._advance_take_queue()
        if self._take_pos >= len(self._take_queue):
            return self._start_next_trick(seat, action)

        return self._obs_for_current(), rewards, False, info

    def _begin_take_phase(self, leader_idx: int, last_seat: int, last_action: Action):
        assert self.game is not None
        leader_idx = self.game.ensure_leader_active(leader_idx)
        # Heads-up: takes disabled (same as ThullaGame.take_phase).
        if leader_idx is None or len(self.game.active_player_indices) <= 2:
            return self._start_next_trick(last_seat, last_action, leader_override=leader_idx)

        self.phase = "take"
        self._take_leader = leader_idx
        self.leader = leader_idx
        self.trick = None
        self.game.info.sync_hands(self.game.players)
        self._take_queue = [
            idx
            for idx in self.game.active_in_order(leader_idx)
            if self.game.take_offer_context(leader_idx, idx) is not None
        ]
        self._take_pos = 0
        if not self._take_queue:
            return self._start_next_trick(last_seat, last_action)

        rewards = np.zeros(self.num_players, dtype=np.float32)
        info = {"seat": last_seat, "action": last_action, "phase": "play"}
        return self._obs_for_current(), rewards, False, info

    def _advance_take_queue(self):
        """Drop seats that can no longer take (got away / heads-up)."""
        assert self.game is not None and self._take_leader is not None
        while self._take_pos < len(self._take_queue):
            seat = self._take_queue[self._take_pos]
            if self.game.take_offer_context(self._take_leader, seat) is None:
                self._take_pos += 1
                continue
            if len(self.game.active_player_indices) <= 2:
                self._take_pos = len(self._take_queue)
                return
            break

    def _start_next_trick(
        self,
        last_seat: int,
        last_action: Action,
        leader_override: int | None = None,
    ):
        assert self.game is not None
        leader = leader_override if leader_override is not None else self.leader
        leader = self.game.ensure_leader_active(leader)
        if self._is_finished(leader):
            return self._terminal(last_seat, last_action)

        self.phase = "play"
        self._take_queue = []
        self._take_pos = 0
        self._take_leader = None
        self.leader = leader
        self.trick = self.game.begin_trick(self.leader, first_trick=False)
        if self.trick is None or self._is_finished(self.leader):
            return self._terminal(last_seat, last_action)

        rewards = np.zeros(self.num_players, dtype=np.float32)
        info = {"seat": last_seat, "action": last_action}
        return self._obs_for_current(), rewards, False, info

    def _is_finished(self, leader_idx) -> bool:
        assert self.game is not None
        return leader_idx is None or len(self.game.active_player_indices) <= 1

    def _terminal(self, seat: int, action: Action):
        rewards = self._finish_rewards()
        self._seat_returns = {i: float(rewards[i]) for i in range(self.num_players)}
        return None, rewards, True, {"seat": seat, "action": action, "finish": True}

    def _finish_rewards(self) -> np.ndarray:
        """Map finishing order to FINISH_REWARDS."""
        assert self.game is not None
        rewards = np.zeros(self.num_players, dtype=np.float32)
        order: list[int] = []
        for p in self.game.winners:
            order.append(self.game.players.index(p))
        leftover = list(self.game.active_player_indices)
        for idx in leftover:
            if idx not in order:
                order.append(idx)
        for i in range(self.num_players):
            if i not in order:
                order.append(i)
        order = order[: self.num_players]
        for place, seat in enumerate(order):
            rewards[seat] = FINISH_REWARDS[min(place, len(FINISH_REWARDS) - 1)]
        return rewards

    def encode_played_action(self, action: Action) -> np.ndarray:
        return encode_action(action)
