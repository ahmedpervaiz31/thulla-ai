"""CLI / notebook arguments for Thulla DMC."""

from __future__ import annotations

import argparse


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Thulla DMC (minimal DouZero-style)")
    p.add_argument("--xpid", default="thulla_dmc")
    p.add_argument("--savedir", default="thulla_dmc_checkpoints")
    p.add_argument(
        "--save_interval",
        default=3,
        type=float,
        help="Minutes between Drive/local latest checkpoints (default: 3)",
    )
    p.add_argument("--load_model", action="store_true")
    p.add_argument("--disable_checkpoint", action="store_true")
    p.add_argument(
        "--training_device",
        default="0",
        help="'cpu' or GPU index. Colab T4: use '0'",
    )
    p.add_argument(
        "--num_actors",
        default=6,
        type=int,
        help="Self-play actor processes (CPU). T4 Colab: 4–8 is typical",
    )
    p.add_argument(
        "--batch_size",
        default=512,
        type=int,
        help="Transitions per learn step (T4 can take 512–1024)",
    )
    p.add_argument("--total_episodes", default=50000, type=int)
    p.add_argument("--exp_epsilon", default=0.05, type=float)
    p.add_argument("--learning_rate", default=1e-4, type=float)
    p.add_argument("--max_grad_norm", default=40.0, type=float)
    p.add_argument("--log_interval", default=25, type=int, help="Episodes between log lines")
    p.add_argument(
        "--eval_random_minutes",
        default=15.0,
        type=float,
        help="Minutes between eval vs RandomPlayer (0=off)",
    )
    p.add_argument(
        "--eval_heuristic_minutes",
        default=30.0,
        type=float,
        help="Minutes between eval vs ComputerPlayer (0=off)",
    )
    p.add_argument(
        "--eval_games",
        default=50,
        type=int,
        help="Games per timed eval (random and heuristic)",
    )
    p.add_argument(
        "--require_gpu",
        action="store_true",
        help="Abort if CUDA is unavailable (recommended on Colab T4)",
    )
    return p


def parse_args(argv=None):
    return parser().parse_args(argv)
