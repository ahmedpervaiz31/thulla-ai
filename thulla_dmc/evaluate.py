"""Evaluate a Thulla DMC checkpoint vs RandomPlayer or ComputerPlayer."""

from __future__ import annotations

import argparse
import os
import random

import numpy as np
import torch

from thulla.cards import valid_moves
from thulla.game import ThullaGame
from thulla.players import BasePlayer, ComputerPlayer, RandomPlayer

from .encode import ASK, PASS, build_action_batch, encode_state
from .env import FINISH_REWARDS
from .models import Model

# Faster ComputerPlayer for periodic training evals (full 200 is slow on Colab).
EVAL_HEURISTIC_MC_SAMPLES = 50


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


def _make_opponent(kind: str, name: str, mc_samples: int):
    if kind == "random":
        return RandomPlayer(name)
    if kind == "heuristic":
        return ComputerPlayer(name, mc_samples=mc_samples)
    raise ValueError(f"unknown opponent kind {kind!r}")


def _run_game(
    dmc: DMCPlayer,
    dmc_seat: int,
    seed: int | None = None,
    *,
    opponent: str = "random",
    heuristic_mc_samples: int = EVAL_HEURISTIC_MC_SAMPLES,
) -> tuple[int, float]:
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
            players.append(_make_opponent(opponent, f"O{i}", heuristic_mc_samples))
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


def evaluate_model(
    model: Model,
    num_games: int = 50,
    *,
    opponent: str = "random",
    dmc_seat: int = 0,
    seed0: int = 10_000,
    heuristic_mc_samples: int = EVAL_HEURISTIC_MC_SAMPLES,
) -> dict:
    """Run eval games for an in-memory model (CPU recommended)."""
    model.eval()
    dmc = DMCPlayer("DMC", model, torch.device("cpu"))
    places = []
    rewards = []
    for g in range(num_games):
        place, reward = _run_game(
            dmc,
            dmc_seat,
            seed=seed0 + g,
            opponent=opponent,
            heuristic_mc_samples=heuristic_mc_samples,
        )
        places.append(place)
        rewards.append(reward)

    places_a = np.array(places)
    not_last = float(np.mean(places_a < 3))
    return {
        "opponent": opponent,
        "num_games": num_games,
        "p_not_last": not_last,
        "p_last": float(1.0 - not_last),
        "mean_reward": float(np.mean(rewards)),
        "places": places_a.tolist(),
    }


def evaluate(
    checkpoint: str,
    num_games: int = 400,
    device: str = "cpu",
    dmc_seat: int = 0,
    opponent: str = "random",
):
    dev = torch.device(device if device != "cpu" and torch.cuda.is_available() else "cpu")
    model = Model(device="cpu" if dev.type == "cpu" else device)
    state = torch.load(checkpoint, map_location=dev)
    if isinstance(state, dict) and "model_state_dict" in state:
        model.load_state_dict(state["model_state_dict"])
    else:
        model.load_state_dict(state)
    # Always score on CPU for consistent / simpler eval.
    cpu_model = Model(device="cpu")
    cpu_model.load_state_dict({k: v.detach().cpu() for k, v in model.state_dict().items()})
    result = evaluate_model(
        cpu_model,
        num_games,
        opponent=opponent,
        dmc_seat=dmc_seat,
    )
    baseline = "~0.75" if opponent == "random" else "vs ComputerPlayer (fair ~0.75 if equal)"
    print(f"Opponent: {opponent}  Games: {num_games}")
    print(f"P(not last): {result['p_not_last']:.3f}  (baseline {baseline})")
    print(f"P(last):     {result['p_last']:.3f}")
    print(f"Mean reward: {result['mean_reward']:.3f}")
    print(
        f"Finish histogram (0=1st … 3=last): "
        f"{np.bincount(result['places'], minlength=4).tolist()}"
    )
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Evaluate Thulla DMC")
    p.add_argument("--checkpoint", required=True, help="Path to model.tar or player.ckpt")
    p.add_argument("--num_games", type=int, default=400)
    p.add_argument("--device", default="cpu")
    p.add_argument("--dmc_seat", type=int, default=0)
    p.add_argument(
        "--opponent",
        default="random",
        choices=["random", "heuristic"],
        help="Other three seats: RandomPlayer or ComputerPlayer",
    )
    args = p.parse_args(argv)
    if not os.path.exists(args.checkpoint):
        raise SystemExit(f"Missing checkpoint: {args.checkpoint}")
    evaluate(
        args.checkpoint,
        args.num_games,
        args.device,
        args.dmc_seat,
        opponent=args.opponent,
    )


if __name__ == "__main__":
    main()
