"""Minimal Deep Monte Carlo training loop for Thulla."""

from __future__ import annotations

import logging
import os
import time
import timeit
from queue import Empty

import numpy as np
import torch
import torch.multiprocessing as mp
from torch import nn

from .arguments import parse_args
from .encode import X_DIM, Z_DIM, Z_ROWS
from .models import Model

log = logging.getLogger("thulla_dmc")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(levelname)s %(asctime)s] %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    log.propagate = False


def _device_of(flags) -> torch.device:
    if flags.training_device == "cpu" or not torch.cuda.is_available():
        return torch.device("cpu")
    return torch.device(f"cuda:{flags.training_device}")


def select_action(model: Model, obs: dict, device: torch.device, exp_epsilon: float):
    z = torch.from_numpy(obs["z_batch"]).float().to(device)
    x = torch.from_numpy(obs["x_batch"]).float().to(device)
    with torch.no_grad():
        out = model.forward(z, x, exp_epsilon=exp_epsilon)
    idx = int(out["action"].detach().cpu().item())
    return obs["legal_actions"][idx], idx


def play_episode(model: Model, device: torch.device, exp_epsilon: float) -> list[dict]:
    """Play one self-play game; return transitions with finish-rank targets."""
    import random as _random

    from .rust_env import RustThullaEnv, make_env

    env = make_env(prefer_rust=True)
    if isinstance(env, RustThullaEnv):
        obs = env.reset(seed=_random.getrandbits(63))
    else:
        obs = env.reset()
    steps: list[dict] = []

    while True:
        seat = obs["position"]
        action, _ = select_action(model, obs, device, exp_epsilon)
        transition = {
            "seat": seat,
            "x_no_action": obs["x_no_action"].copy(),
            "z": obs["z"].copy(),
            "action": env.encode_played_action(action).copy(),
        }
        obs, rewards, done, _info = env.step(action)
        steps.append(transition)
        if done:
            for t in steps:
                t["target"] = float(rewards[t["seat"]])
            return steps


def _actor_loop(actor_id: int, weight_queue, out_queue, stop_queue, exp_epsilon: float):
    """Actor process: pull latest CPU weights, play episodes, push transitions."""
    device = torch.device("cpu")
    model = Model(device="cpu")
    model.eval()
    while stop_queue.empty():
        try:
            while True:
                state = weight_queue.get_nowait()
                model.load_state_dict(state)
        except Empty:
            pass
        try:
            steps = play_episode(model, device, exp_epsilon)
            out_queue.put(steps)
        except Exception as exc:
            log.error("Actor %s failed: %s", actor_id, exc)
            raise


def _checkpoint_paths(flags) -> dict[str, str]:
    root = os.path.join(flags.savedir, flags.xpid)
    os.makedirs(root, exist_ok=True)
    return {
        "root": root,
        "main": os.path.join(root, "model.tar"),
        "latest": os.path.join(root, "model_latest.tar"),
        "best": os.path.join(root, "model_best.tar"),
        "weights": os.path.join(root, "player.ckpt"),
        "best_weights": os.path.join(root, "player_best.ckpt"),
        "eval_log": os.path.join(root, "eval_log.csv"),
    }


_EVAL_LOG_HEADER = (
    "timestamp,episodes,opponent,games,p_not_last,p_last,mean_reward,is_best,eval_seed\n"
)


def append_eval_log(flags, episodes: int, ev: dict, *, is_best: bool = False) -> str:
    """Append one summary row to eval_log.csv in the checkpoint folder (Drive)."""
    paths = _checkpoint_paths(flags)
    path = paths["eval_log"]
    new_file = not os.path.exists(path)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    seed = ev.get("eval_seed", getattr(flags, "eval_seed", ""))
    row = (
        f"{ts},{episodes},{ev.get('opponent','')},{ev.get('num_games',0)},"
        f"{ev.get('p_not_last',0):.4f},{ev.get('p_last',0):.4f},"
        f"{ev.get('mean_reward',0):.4f},{int(bool(is_best))},{seed}\n"
    )
    with open(path, "a", encoding="utf-8") as f:
        if new_file:
            f.write(_EVAL_LOG_HEADER)
        f.write(row)
    return path


def save_checkpoint(flags, learner: Model, optimizer, episodes: int, stats: dict, *, best: bool = False):
    if flags.disable_checkpoint:
        return
    paths = _checkpoint_paths(flags)
    payload = {
        "model_state_dict": learner.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "episodes": episodes,
        "stats": stats,
        "flags": vars(flags) if hasattr(flags, "__dict__") else dict(flags),
    }
    if best:
        torch.save(payload, paths["best"])
        torch.save(learner.state_dict(), paths["best_weights"])
        log.info(
            "Saved BEST checkpoint → %s (episodes=%s P(not last) vs heuristic=%.3f)",
            paths["best"],
            episodes,
            stats.get("p_not_last_heuristic", 0.0),
        )
    else:
        torch.save(payload, paths["main"])
        torch.save(payload, paths["latest"])
        torch.save(learner.state_dict(), paths["weights"])
        log.info("Saved checkpoint → %s (episodes=%s)", paths["main"], episodes)


def load_checkpoint(flags, learner: Model, optimizer, device: torch.device):
    paths = _checkpoint_paths(flags)
    path = paths["main"] if os.path.exists(paths["main"]) else (
        paths["latest"] if os.path.exists(paths["latest"]) else None
    )
    if path is None:
        log.info("No checkpoint found under %s", paths["root"])
        return 0, {}
    data = torch.load(path, map_location=device)
    learner.load_state_dict(data["model_state_dict"])
    if "optimizer_state_dict" in data:
        try:
            optimizer.load_state_dict(data["optimizer_state_dict"])
        except Exception:
            log.warning("Optimizer state not restored; continuing with fresh optimizer")
    episodes = int(data.get("episodes", 0))
    stats = data.get("stats", {})
    log.info("Resumed from %s (episodes=%s)", path, episodes)
    return episodes, stats


def learn_batch(learner: Model, optimizer, batch: list[dict], device: torch.device, max_grad_norm: float):
    if not batch:
        return 0.0
    non_blocking = device.type == "cuda"
    x_no = torch.from_numpy(np.stack([b["x_no_action"] for b in batch])).float()
    actions = torch.from_numpy(np.stack([b["action"] for b in batch])).float()
    z = torch.from_numpy(np.stack([b["z"] for b in batch])).float()
    targets = torch.tensor([b["target"] for b in batch], dtype=torch.float32)
    if non_blocking:
        x_no = x_no.pin_memory().to(device, non_blocking=True)
        actions = actions.pin_memory().to(device, non_blocking=True)
        z = z.pin_memory().to(device, non_blocking=True)
        targets = targets.pin_memory().to(device, non_blocking=True)
    else:
        x_no = x_no.to(device)
        actions = actions.to(device)
        z = z.to(device)
        targets = targets.to(device)
    x = torch.cat([x_no, actions], dim=-1)
    assert x.shape[-1] == X_DIM
    assert z.shape[1:] == (Z_ROWS, Z_DIM)

    learner.train()
    out = learner.forward(z, x, return_value=True)
    values = out["values"].squeeze(-1)
    loss = ((values - targets) ** 2).mean()
    optimizer.zero_grad()
    loss.backward()
    nn.utils.clip_grad_norm_(learner.parameters(), max_grad_norm)
    optimizer.step()
    learner.eval()
    return float(loss.item())


def _cpu_copy(learner: Model) -> Model:
    cpu_model = Model(device="cpu")
    cpu_model.load_state_dict({k: v.detach().cpu() for k, v in learner.state_dict().items()})
    cpu_model.eval()
    return cpu_model


def run_timed_eval(
    learner: Model,
    opponent: str,
    num_games: int,
    *,
    eval_seed: int = 10_000,
) -> dict:
    from .evaluate import evaluate_model

    return evaluate_model(
        _cpu_copy(learner),
        num_games,
        opponent=opponent,
        eval_seed=eval_seed,
    )


def train(flags=None):
    """Main entry: spawn actors, learn from episode queues, checkpoint often."""
    if flags is None:
        flags = parse_args([])
    try:
        mp.set_start_method("spawn", force=True)
    except RuntimeError:
        pass

    if getattr(flags, "require_gpu", False) and not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA required (--require_gpu) but not available. "
            "In Colab: Runtime → Change runtime type → T4 GPU."
        )

    device = _device_of(flags)
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True
        gpu_name = torch.cuda.get_device_name(device)
        log.info(
            "GPU learner: %s (%s) | actors=%s | batch=%s | "
            "eval random every %s min | heuristic every %s min (%s games, seed=%s)",
            device,
            gpu_name,
            flags.num_actors,
            flags.batch_size,
            flags.eval_random_minutes,
            flags.eval_heuristic_minutes,
            flags.eval_games,
            getattr(flags, "eval_seed", 10_000),
        )
    else:
        log.info(
            "Training on %s | actors=%s | batch=%s | eval_seed=%s",
            device,
            flags.num_actors,
            flags.batch_size,
            getattr(flags, "eval_seed", 10_000),
        )

    learner = Model(device="cpu" if device.type == "cpu" else flags.training_device)
    learner.train()
    optimizer = torch.optim.RMSprop(learner.parameters(), lr=flags.learning_rate)

    episodes_done = 0
    stats = {
        "loss": 0.0,
        "mean_return": 0.0,
        "p_not_last_random": 0.0,
        "p_not_last_heuristic": 0.0,
        "best_p_not_last_heuristic": -1.0,
    }
    if flags.load_model:
        episodes_done, loaded = load_checkpoint(flags, learner, optimizer, device)
        stats.update(loaded or {})

    ctx_weight: mp.Queue = mp.Queue(maxsize=flags.num_actors * 2)
    out_queue: mp.Queue = mp.Queue(maxsize=64)
    stop_queue: mp.Queue = mp.Queue()

    def push_weights():
        state = {k: v.detach().cpu().clone() for k, v in learner.state_dict().items()}
        for _ in range(flags.num_actors):
            try:
                ctx_weight.put_nowait(state)
            except Exception:
                break

    push_weights()
    actors = []
    for i in range(flags.num_actors):
        p = mp.Process(
            target=_actor_loop,
            args=(i, ctx_weight, out_queue, stop_queue, flags.exp_epsilon),
            daemon=True,
        )
        p.start()
        actors.append(p)

    buffer: list[dict] = []
    returns_window: list[float] = []
    timer = timeit.default_timer
    last_ckpt = timer()
    last_log = episodes_done
    last_eval_random = timer()
    last_eval_heuristic = timer()

    try:
        while episodes_done < flags.total_episodes:
            steps = out_queue.get()
            buffer.extend(steps)
            returns_window.extend(t["target"] for t in steps)
            if len(returns_window) > 2000:
                returns_window = returns_window[-2000:]
            episodes_done += 1

            while len(buffer) >= flags.batch_size:
                batch = buffer[: flags.batch_size]
                buffer = buffer[flags.batch_size :]
                loss = learn_batch(learner, optimizer, batch, device, flags.max_grad_norm)
                stats["loss"] = loss
                stats["mean_return"] = float(np.mean(returns_window)) if returns_window else 0.0
                push_weights()

            if episodes_done - last_log >= flags.log_interval:
                log.info(
                    "episodes=%s loss=%.4f mean_target=%.3f buffer=%s "
                    "P(not last) random=%.3f heuristic=%.3f best_h=%.3f",
                    episodes_done,
                    stats.get("loss", 0.0),
                    stats.get("mean_return", 0.0),
                    len(buffer),
                    stats.get("p_not_last_random", 0.0),
                    stats.get("p_not_last_heuristic", 0.0),
                    stats.get("best_p_not_last_heuristic", 0.0),
                )
                last_log = episodes_done

            now = timer()
            if (
                flags.eval_random_minutes > 0
                and (now - last_eval_random) >= flags.eval_random_minutes * 60
            ):
                ev = run_timed_eval(
                    learner,
                    "random",
                    flags.eval_games,
                    eval_seed=getattr(flags, "eval_seed", 10_000),
                )
                stats["p_not_last_random"] = ev["p_not_last"]
                log_path = append_eval_log(flags, episodes_done, ev, is_best=False)
                log.info(
                    "EVAL vs random  episodes=%s games=%s seed=%s P(not last)=%.3f P(last)=%.3f "
                    "mean_reward=%.3f (random≈0.75) → %s",
                    episodes_done,
                    flags.eval_games,
                    ev.get("eval_seed", getattr(flags, "eval_seed", "")),
                    ev["p_not_last"],
                    ev["p_last"],
                    ev["mean_reward"],
                    log_path,
                )
                last_eval_random = timer()
                push_weights()

            if (
                flags.eval_heuristic_minutes > 0
                and (now - last_eval_heuristic) >= flags.eval_heuristic_minutes * 60
            ):
                ev = run_timed_eval(
                    learner,
                    "heuristic",
                    flags.eval_games,
                    eval_seed=getattr(flags, "eval_seed", 10_000),
                )
                stats["p_not_last_heuristic"] = ev["p_not_last"]
                best = float(stats.get("best_p_not_last_heuristic", -1.0))
                is_best = ev["p_not_last"] > best
                if is_best:
                    stats["best_p_not_last_heuristic"] = ev["p_not_last"]
                    save_checkpoint(
                        flags, learner, optimizer, episodes_done, stats, best=True
                    )
                log_path = append_eval_log(flags, episodes_done, ev, is_best=is_best)
                log.info(
                    "EVAL vs heuristic  episodes=%s games=%s seed=%s P(not last)=%.3f P(last)=%.3f "
                    "mean_reward=%.3f best=%s → %s",
                    episodes_done,
                    flags.eval_games,
                    ev.get("eval_seed", getattr(flags, "eval_seed", "")),
                    ev["p_not_last"],
                    ev["p_last"],
                    ev["mean_reward"],
                    is_best,
                    log_path,
                )
                last_eval_heuristic = timer()
                push_weights()

            if (timer() - last_ckpt) >= flags.save_interval * 60:
                save_checkpoint(flags, learner, optimizer, episodes_done, stats)
                last_ckpt = timer()

    except KeyboardInterrupt:
        log.info("Interrupted — saving checkpoint")
    finally:
        stop_queue.put(True)
        for p in actors:
            p.join(timeout=2)
            if p.is_alive():
                p.terminate()
        save_checkpoint(flags, learner, optimizer, episodes_done, stats)
        log.info("Done after %s episodes", episodes_done)


if __name__ == "__main__":
    train(parse_args())
