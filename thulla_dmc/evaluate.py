"""Evaluate a Thulla DMC checkpoint vs RandomPlayer (P(not last))."""

from __future__ import annotations

import argparse
import os
import random

import numpy as np
import torch

from thulla.cards import valid_moves
from thulla.game import ThullaGame
from thulla.players import BasePlayer, RandomPlayer

from .encode import ASK, PASS, build_action_batch, encode_state
from .env import FINISH_REWARDS
from .models import Model


class DMCPlayer(BasePlayer):
    """Greedy DMC policy for evaluation / mixed games (cards + ASK/PASS)."""

    def __init__(self, name, model: Model, device: torch.device):
        super().__init__(name)
        self.model = model
        self.device = device
        self.play_history = []
        self.game: ThullaGame | None = None

    def reset_history(self):
        self.play_history = []

    def note_played(self, card):
        self.play_history.append(card)

    def play_turn(self, expected_cards, view=None):
        raise RuntimeError("Use choose() via evaluate harness")

    def _pick(self, legal, *, trick, take_phase: bool, i_am_leader: bool = False):
        assert self.game is not None
        seat = self.game.players.index(self)
        x_no, z = encode_state(
            self.game,
            seat,
            trick,
            self.play_history,
            take_phase=take_phase,
            i_am_leader=i_am_leader,
        )
        x_batch, z_batch = build_action_batch(x_no, z, legal)
        z_t = torch.from_numpy(z_batch).float().to(self.device)
        x_t = torch.from_numpy(x_batch).float().to(self.device)
        with torch.no_grad():
            out = self.model.forward(z_t, x_t, exp_epsilon=0.0)
        idx = int(out["action"].detach().cpu().item())
        return legal[idx]

    def choose(self, game, trick, expected_cards):
        self.game = game
        legal = valid_moves(self.hand, expected_cards)
        card = self._pick(legal, trick=trick, take_phase=False)
        self.hand.remove(card)
        return card

    def offer_take(self, target_name, n_cards, view=None, neighbor_idx=None, i_am_leader=False):
        if self.game is None:
            return False
        action = self._pick(
            [ASK, PASS],
            trick=None,
            take_phase=True,
            i_am_leader=bool(i_am_leader),
        )
        return action == ASK

    def offer_give(self, asker_name, n_cards, view=None, asker_idx=None):
        return True


class _ScriptedGame(ThullaGame):
    """Like ThullaGame.resolve_trick but routes DMC seats through choose()."""

    def resolve_trick(self, leader_idx, first_trick=False):
        trick = self.begin_trick(leader_idx, first_trick=first_trick)
        if trick is None:
            return None
        while not trick.done:
            turn_idx = trick.order[trick.seat_pos]
            player = self.players[turn_idx]
            expected = self.expected_for_seat(trick, turn_idx)
            if isinstance(player, DMCPlayer):
                card = player.choose(self, trick, expected)
            else:
                view = self.view_for_seat(trick, turn_idx)
                card = player.play_turn(expected, view)
            self.apply_play(trick, turn_idx, card)
            for p in self.players:
                if isinstance(p, DMCPlayer):
                    p.note_played(card)
        return trick.next_leader


def _run_game(dmc: DMCPlayer, dmc_seat: int, seed: int | None = None) -> tuple[int, float]:
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
    players = []
    for i in range(4):
        if i == dmc_seat:
            players.append(dmc)
            dmc.name = f"DMC{i}"
            dmc.hand = []
            dmc.reset_history()
        else:
            players.append(RandomPlayer(f"R{i}"))
    game = _ScriptedGame(players, verbose=False)
    dmc.game = game
    game.shuffle_and_deal()
    leader = game.ace_spades_holder_idx
    game.resolve_trick(leader, first_trick=True)
    leader = game.check_got_away(game.ace_spades_holder_idx)
    while len(game.active_player_indices) > 1:
        leader = game.take_phase(leader)
        if leader is None or len(game.active_player_indices) <= 1:
            break
        leader = game.resolve_trick(leader, first_trick=False)
        leader = game.check_got_away(leader)

    order = []
    for p in game.winners:
        order.append(game.players.index(p))
    for idx in game.active_player_indices:
        if idx not in order:
            order.append(idx)
    place = order.index(dmc_seat)  # 0 = first away
    reward = FINISH_REWARDS[min(place, len(FINISH_REWARDS) - 1)]
    return place, reward


def evaluate(checkpoint: str, num_games: int = 400, device: str = "cpu", dmc_seat: int = 0):
    dev = torch.device(device if device != "cpu" and torch.cuda.is_available() else "cpu")
    model = Model(device="cpu" if dev.type == "cpu" else device)
    state = torch.load(checkpoint, map_location=dev)
    if isinstance(state, dict) and "model_state_dict" in state:
        model.load_state_dict(state["model_state_dict"])
    else:
        model.load_state_dict(state)
    model.eval()
    dmc = DMCPlayer("DMC", model, dev)

    places = []
    rewards = []
    for g in range(num_games):
        place, reward = _run_game(dmc, dmc_seat, seed=10_000 + g)
        places.append(place)
        rewards.append(reward)

    places = np.array(places)
    not_last = float(np.mean(places < 3))
    mean_reward = float(np.mean(rewards))
    print(f"Games: {num_games}")
    print(f"P(not last): {not_last:.3f}  (random baseline ~0.75)")
    print(f"P(last):     {1 - not_last:.3f}  (random baseline ~0.25)")
    print(f"Mean reward: {mean_reward:.3f}")
    print(f"Finish histogram (0=1st … 3=last): {np.bincount(places, minlength=4).tolist()}")
    return {"p_not_last": not_last, "mean_reward": mean_reward, "places": places.tolist()}


def main(argv=None):
    p = argparse.ArgumentParser(description="Evaluate Thulla DMC vs RandomPlayer")
    p.add_argument("--checkpoint", required=True, help="Path to model.tar or player.ckpt")
    p.add_argument("--num_games", type=int, default=400)
    p.add_argument("--device", default="cpu")
    p.add_argument("--dmc_seat", type=int, default=0)
    args = p.parse_args(argv)
    if not os.path.exists(args.checkpoint):
        raise SystemExit(f"Missing checkpoint: {args.checkpoint}")
    evaluate(args.checkpoint, args.num_games, args.device, args.dmc_seat)


if __name__ == "__main__":
    main()
