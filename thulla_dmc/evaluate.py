"""Evaluate a Thulla DMC checkpoint vs RandomPlayer or ComputerPlayer."""

from __future__ import annotations

import argparse
import os
import random

import numpy as np
import torch

from thulla.cards import valid_moves
from thulla.game import ThullaGame
from thulla.players import ComputerPlayer, RandomPlayer, choose_computer_card

from .env import FINISH_REWARDS
from .models import Model
from .player import DMCPlayer, load_model

# Faster ComputerPlayer for periodic training evals (full 200 is slow on Colab).
EVAL_HEURISTIC_MC_SAMPLES = 50

# Fixed deal/MC bank so checkpoint A vs B compares the same games (apples-to-apples).
# Game i → eval_seed + i (same formula historically used as seed0+g in training evals).
DEFAULT_EVAL_SEED = 10_000


def eval_game_seeds(
    num_games: int,
    *,
    opponent: str = "random",
    eval_seed: int = DEFAULT_EVAL_SEED,
) -> list[int]:
    """Deterministic seed list for timed / CLI evals (opponent unused; kept for API clarity)."""
    del opponent  # banks are shared; opponents diverge after the deal
    base = int(eval_seed)
    return [base + g for g in range(int(num_games))]


def _seed_everything(seed: int) -> None:
    """Deal + heuristic MC + any torch noise all follow this seed."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


class _ScriptedGame(ThullaGame):
    """Like ThullaGame.resolve_trick but routes DMC seats through choose()."""

    def __init__(
        self,
        players,
        *,
        verbose: bool = False,
        agree_stats: dict | None = None,
        heur_mc_samples: int = EVAL_HEURISTIC_MC_SAMPLES,
    ):
        super().__init__(players, verbose=verbose)
        self._agree_stats = agree_stats
        self._heur_mc_samples = int(heur_mc_samples)

    def resolve_trick(self, leader_idx, first_trick=False):
        trick = self.begin_trick(leader_idx, first_trick=first_trick)
        if trick is None:
            return None
        while not trick.done:
            turn_idx = trick.order[trick.seat_pos]
            player = self.players[turn_idx]
            expected = self.expected_for_seat(trick, turn_idx)
            if isinstance(player, DMCPlayer):
                card = player.select_card(self, trick, expected)
                if self._agree_stats is not None:
                    view = self.view_for_seat(trick, turn_idx)
                    moves = valid_moves(player.hand, expected)
                    h_card = choose_computer_card(
                        player.hand,
                        moves,
                        expected,
                        view,
                        samples=self._heur_mc_samples,
                    )
                    self._agree_stats["n"] = int(self._agree_stats.get("n", 0)) + 1
                    if h_card == card:
                        self._agree_stats["agree"] = (
                            int(self._agree_stats.get("agree", 0)) + 1
                        )
                player.hand.remove(card)
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
    agree_stats: dict | None = None,
) -> tuple[int, float]:
    if seed is not None:
        _seed_everything(int(seed))
    players = []
    for i in range(4):
        if i == dmc_seat:
            players.append(dmc)
            dmc.name = f"DMC{i}"
            dmc.hand = []
            dmc.reset_history()
        else:
            players.append(_make_opponent(opponent, f"O{i}", heuristic_mc_samples))
    game = _ScriptedGame(
        players,
        verbose=False,
        agree_stats=agree_stats,
        heur_mc_samples=heuristic_mc_samples,
    )
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
    eval_seed: int = DEFAULT_EVAL_SEED,
    seed0: int | None = None,
    heuristic_mc_samples: int = EVAL_HEURISTIC_MC_SAMPLES,
    track_heur_agree: bool | None = None,
) -> dict:
    """
    Run eval games for an in-memory model (CPU recommended).

    Uses a fixed seed bank so the same (opponent, num_games, eval_seed) always
    replays the same deals / heuristic MC rolls — comparable across checkpoints.
    ``seed0`` is accepted as an alias for ``eval_seed`` (legacy).

    When ``track_heur_agree`` is True, each DMC card play is compared to what
    ``ComputerPlayer`` would pick on the same state (diagnostic; not a loss).
    Default: enabled only for ``opponent="heuristic"`` (keeps random evals fast).
    """
    if seed0 is not None:
        eval_seed = seed0
    if track_heur_agree is None:
        track_heur_agree = opponent == "heuristic"
    seeds = eval_game_seeds(num_games, opponent=opponent, eval_seed=eval_seed)    model.eval()
    dmc = DMCPlayer("DMC", model, torch.device("cpu"))
    places = []
    rewards = []
    agree_stats: dict | None = {"n": 0, "agree": 0} if track_heur_agree else None
    for seed in seeds:
        place, reward = _run_game(
            dmc,
            dmc_seat,
            seed=seed,
            opponent=opponent,
            heuristic_mc_samples=heuristic_mc_samples,
            agree_stats=agree_stats,
        )
        places.append(place)
        rewards.append(reward)

    places_a = np.array(places)
    not_last = float(np.mean(places_a < 3))
    n_cmp = int(agree_stats["n"]) if agree_stats else 0
    n_agree = int(agree_stats["agree"]) if agree_stats else 0
    heur_agree = float(n_agree / n_cmp) if n_cmp > 0 else float("nan")
    return {
        "opponent": opponent,
        "num_games": num_games,
        "eval_seed": int(eval_seed),
        "seed0": int(seeds[0]) if seeds else int(eval_seed),
        "p_not_last": not_last,
        "p_last": float(1.0 - not_last),
        "mean_reward": float(np.mean(rewards)),
        "places": places_a.tolist(),
        "heur_agree": heur_agree,
        "heur_agree_n": n_cmp,
        "heur_agree_hits": n_agree,
    }


def evaluate(
    checkpoint: str,
    num_games: int = 400,
    device: str = "cpu",
    dmc_seat: int = 0,
    opponent: str = "random",
    eval_seed: int = DEFAULT_EVAL_SEED,
):
    model = load_model(checkpoint, device=device)
    result = evaluate_model(
        model,
        num_games,
        opponent=opponent,
        dmc_seat=dmc_seat,
        eval_seed=eval_seed,
    )
    baseline = "~0.75" if opponent == "random" else "vs ComputerPlayer (fair ~0.75 if equal)"
    print(f"Opponent: {opponent}  Games: {num_games}  eval_seed: {eval_seed}")
    print(f"P(not last): {result['p_not_last']:.3f}  (baseline {baseline})")
    print(f"P(last):     {result['p_last']:.3f}")
    print(f"Mean reward: {result['mean_reward']:.3f}")
    print(
        f"Finish histogram (0=1st … 3=last): "
        f"{np.bincount(result['places'], minlength=4).tolist()}"
    )
    if result.get("heur_agree_n", 0) > 0:
        print(
            f"Heuristic pick agree: {result['heur_agree']:.3f} "
            f"({result['heur_agree_hits']}/{result['heur_agree_n']} card plays)"
        )
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Evaluate Thulla DMC")
    p.add_argument("--checkpoint", required=True, help="Path to model.tar or player.ckpt")
    p.add_argument("--num_games", type=int, default=400)
    p.add_argument("--device", default="cpu")
    p.add_argument("--dmc_seat", type=int, default=0)
    p.add_argument(
        "--eval_seed",
        type=int,
        default=DEFAULT_EVAL_SEED,
        help="Fixed seed bank base (game i → eval_seed+i)",
    )
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
        eval_seed=args.eval_seed,
    )


if __name__ == "__main__":
    main()
