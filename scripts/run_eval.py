#!/usr/bin/env python3
"""Run Thulla bot evals: P(thulla) calibration + strength."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thulla.eval.instrumented import EVAL_MC_SAMPLES
from thulla.eval.runner import (
    print_calibrate_report,
    print_strength_report,
    run_calibrate,
    run_strength,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Thulla eval harness")
    parser.add_argument("--calibrate-games", type=int, default=10000)
    parser.add_argument("--strength-games", type=int, default=5000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--samples", type=int, default=EVAL_MC_SAMPLES)
    parser.add_argument(
        "--phase",
        choices=("both", "calibrate", "strength"),
        default="both",
    )
    parser.add_argument(
        "--opponents",
        choices=("random", "self"),
        default="random",
        help="random=3x RandomPlayer; self=3x ComputerPlayer",
    )
    parser.add_argument(
        "--late-take",
        action="store_true",
        help="Enable late neighbor-take compare for the candidate",
    )
    args = parser.parse_args(argv)

    print(
        f"Thulla eval  workers={args.workers}  mc_samples={args.samples}  "
        f"phase={args.phase}  opponents={args.opponents}  late_take={args.late_take}",
        flush=True,
    )

    if args.phase in ("both", "calibrate"):
        cal = run_calibrate(
            n_games=args.calibrate_games,
            workers=args.workers,
            mc_samples=args.samples,
        )
        print_calibrate_report(cal)

    if args.phase in ("both", "strength"):
        strength = run_strength(
            n_games=args.strength_games,
            workers=args.workers,
            mc_samples=args.samples,
            allow_late_take=args.late_take,
            opponents=args.opponents,
        )
        print_strength_report(strength)


if __name__ == "__main__":
    main()
