"""Parallel match runner for Thulla evals."""

from __future__ import annotations

import random
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from thulla.game import ThullaGame
from thulla.players import ComputerPlayer, RandomPlayer
from thulla.eval.instrumented import EVAL_MC_SAMPLES, InstrumentedComputerPlayer
from thulla.eval.metrics import (
    brier_score,
    lose_rate_ci,
    reliability_bins,
    format_reliability_table,
)

PLAYERS = 4
BATCH_SIZE = 50
STRENGTH_SEED_START = 1_000_000


def _loser_index(game):
    leftover = game.remaining_players()
    if not leftover:
        return None
    return game.players.index(leftover[0])


def run_calibrate_game(seed, mc_samples=EVAL_MC_SAMPLES):
    random.seed(seed)
    records = []
    players = [
        InstrumentedComputerPlayer(f"P{i}", i, records, mc_samples=mc_samples)
        for i in range(PLAYERS)
    ]
    for p in players:
        p.table_players = players
    game = ThullaGame(players, verbose=False)
    random.seed(seed)
    game.shuffle_and_deal()
    game.game_loop()
    return records, _loser_index(game)


def _finish_rank(game, seat):
    """1 = first away, ..., PLAYERS = last (loser)."""
    for i, p in enumerate(game.winners):
        if game.players.index(p) == seat:
            return i + 1
    leftover = game.remaining_players()
    if leftover and game.players.index(leftover[0]) == seat:
        return PLAYERS
    return None


def run_strength_game(
    seed,
    mc_samples=EVAL_MC_SAMPLES,
    allow_late_take=False,
    opponents="random",
):
    random.seed(seed)
    candidate_seat = seed % PLAYERS
    players = []
    for i in range(PLAYERS):
        if i == candidate_seat:
            players.append(
                ComputerPlayer(
                    f"Cand{i}",
                    mc_samples=mc_samples,
                    allow_late_take=allow_late_take,
                )
            )
        elif opponents == "self":
            players.append(
                ComputerPlayer(
                    f"CPU{i}",
                    mc_samples=mc_samples,
                    allow_late_take=False,
                )
            )
        else:
            players.append(RandomPlayer(f"Rand{i}"))
    game = ThullaGame(players, verbose=False)
    random.seed(seed)
    game.shuffle_and_deal()
    game.game_loop()
    rank = _finish_rank(game, candidate_seat)
    candidate_lost = rank == PLAYERS
    return candidate_lost, candidate_seat, rank


def _calibrate_batch(args):
    seeds, mc_samples = args
    all_records = []
    seat_losses = [0] * PLAYERS
    games = 0
    for seed in seeds:
        recs, loser = run_calibrate_game(seed, mc_samples=mc_samples)
        all_records.extend(recs)
        if loser is not None:
            seat_losses[loser] += 1
        games += 1
    return all_records, seat_losses, games


def _strength_batch(args):
    seeds, mc_samples, allow_late_take, opponents = args
    losses = 0
    games = 0
    rank_counts = [0] * (PLAYERS + 1)
    for seed in seeds:
        lost, _, rank = run_strength_game(
            seed,
            mc_samples=mc_samples,
            allow_late_take=allow_late_take,
            opponents=opponents,
        )
        if lost:
            losses += 1
        if rank is not None:
            rank_counts[rank] += 1
        games += 1
    return losses, games, rank_counts


def _seed_batches(n_games, batch_size, start_seed=0):
    seeds = list(range(start_seed, start_seed + n_games))
    batches = []
    for i in range(0, len(seeds), batch_size):
        batches.append(seeds[i : i + batch_size])
    return batches


def run_calibrate(n_games=10000, workers=6, mc_samples=EVAL_MC_SAMPLES, batch_size=BATCH_SIZE):
    t0 = time.perf_counter()
    batches = _seed_batches(n_games, batch_size, start_seed=0)
    all_records = []
    seat_losses = [0] * PLAYERS
    games = 0

    if workers <= 1:
        for batch in batches:
            recs, losses, g = _calibrate_batch((batch, mc_samples))
            all_records.extend(recs)
            for i, v in enumerate(losses):
                seat_losses[i] += v
            games += g
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_calibrate_batch, (batch, mc_samples)) for batch in batches]
            for fut in as_completed(futs):
                recs, losses, g = fut.result()
                all_records.extend(recs)
                for i, v in enumerate(losses):
                    seat_losses[i] += v
                games += g

    elapsed = time.perf_counter() - t0
    return {
        "games": games,
        "elapsed": elapsed,
        "games_per_sec": games / elapsed if elapsed else 0.0,
        "records": all_records,
        "brier": brier_score(all_records),
        "reliability": reliability_bins(all_records),
        "seat_losses": seat_losses,
        "decision_samples": len(all_records),
    }


def run_strength(
    n_games=5000,
    workers=6,
    mc_samples=EVAL_MC_SAMPLES,
    batch_size=BATCH_SIZE,
    allow_late_take=False,
    opponents="random",
):
    t0 = time.perf_counter()
    batches = _seed_batches(n_games, batch_size, start_seed=STRENGTH_SEED_START)
    losses = 0
    games = 0
    rank_counts = [0] * (PLAYERS + 1)

    batch_args = [
        (batch, mc_samples, allow_late_take, opponents) for batch in batches
    ]

    if workers <= 1:
        for args in batch_args:
            l, g, ranks = _strength_batch(args)
            losses += l
            games += g
            for i, v in enumerate(ranks):
                rank_counts[i] += v
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_strength_batch, args) for args in batch_args]
            for fut in as_completed(futs):
                l, g, ranks = fut.result()
                losses += l
                games += g
                for i, v in enumerate(ranks):
                    rank_counts[i] += v

    elapsed = time.perf_counter() - t0
    rate, lo, hi = lose_rate_ci(losses, games)
    survive = 1.0 - rate
    s_lo, s_hi = 1.0 - hi, 1.0 - lo
    return {
        "games": games,
        "elapsed": elapsed,
        "games_per_sec": games / elapsed if elapsed else 0.0,
        "losses": losses,
        "lose_rate": rate,
        "ci_low": lo,
        "ci_high": hi,
        "survive_rate": survive,
        "survive_ci_low": s_lo,
        "survive_ci_high": s_hi,
        "rank_counts": rank_counts,
        "allow_late_take": allow_late_take,
        "opponents": opponents,
    }


def print_calibrate_report(result):
    print("\n=== Calibrate (4x bot) ===")
    print(f"games={result['games']}  decisions={result['decision_samples']}")
    print(f"elapsed={result['elapsed']:.1f}s  ({result['games_per_sec']:.1f} games/s)")
    print(f"Brier={result['brier']:.4f}")
    print(format_reliability_table(result["reliability"]))
    total = sum(result["seat_losses"]) or 1
    seats = "  ".join(
        f"P{i}={result['seat_losses'][i]/total:.1%}" for i in range(PLAYERS)
    )
    print(f"seat lose rates: {seats}")


def _print_rank_histogram(rank_counts, n):
    print("Finish positions (1=first away ... 4=last):")
    for rank in range(1, PLAYERS + 1):
        c = rank_counts[rank]
        name = "LAST" if rank == PLAYERS else f"{rank}"
        print(f"  {name}: {c}/{n} ({c / n:.1%})")


def print_strength_report(result):
    opp = result.get("opponents", "random")
    title = "vs 3x bot (self-play)" if opp == "self" else "vs 3 random"
    print(f"\n=== Strength {title} (goal = NOT last) ===")
    print(f"late_take={result.get('allow_late_take', False)}")
    print(f"games={result['games']}  times_last={result['losses']}")
    print(f"elapsed={result['elapsed']:.1f}s  ({result['games_per_sec']:.1f} games/s)")
    print(
        f"P(last)={result['lose_rate']:.3f}  "
        f"95% CI [{result['ci_low']:.3f}, {result['ci_high']:.3f}]"
    )
    print(
        f"P(survive / not last)={result['survive_rate']:.3f}  "
        f"95% CI [{result['survive_ci_low']:.3f}, {result['survive_ci_high']:.3f}]"
    )
    _print_rank_histogram(result["rank_counts"], result["games"] or 1)
    if opp == "self":
        print("Fair self-play baseline: each rank ~25%, P(last)~25%")
    else:
        print("Random baseline: each rank ~25%, P(last)~25%, P(survive)~75%")
    print("Lower P(last) is better. 1st vs 2nd vs 3rd is secondary.")
