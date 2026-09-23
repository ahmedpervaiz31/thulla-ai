"""Optional Rust-accelerated DMC env (engine + encode). Falls back to Python."""

from __future__ import annotations

from typing import Any

import numpy as np

from thulla.cards import Card, parse_card

from .encode import (
    ASK,
    PASS,
    HISTORY_LEN,
    CARD_DIM,
    Action,
    encode_action,
)
from .env import ThullaEnv

try:
    from thulla_rust import RustEnv as _RustEnvNative

    RUST_AVAILABLE = True
except ImportError:
    _RustEnvNative = None
    RUST_AVAILABLE = False


def rust_available() -> bool:
    return RUST_AVAILABLE


def _py_action_from_code(code: int) -> Action:
    if code == 52:
        return ASK
    if code == 53:
        return PASS
    # Match encode card_index: colour*13+rank
    from thulla.cards import COLOUR_CARDS, NUMBER_CARDS, create_deck

    deck = create_deck()
    return deck[code]


def _action_to_code(action: Action) -> int:
    if action == ASK:
        return 52
    if action == PASS:
        return 53
    from .encode import card_index

    assert isinstance(action, Card)
    return card_index(action)


def _reshape_rust_obs(raw: dict) -> dict[str, Any]:
    """Convert RustEnv dict into ThullaEnv-compatible obs."""
    legal = []
    for a in raw["legal_actions"]:
        if a == "ASK":
            legal.append(ASK)
        elif a == "PASS":
            legal.append(PASS)
        else:
            c = parse_card(a)
            if c is None:
                raise ValueError(f"bad legal action from rust: {a!r}")
            legal.append(c)

    x_no = np.asarray(raw["x_no_action"], dtype=np.float32)
    z = np.asarray(raw["z"], dtype=np.float32)
    x_batch = np.asarray(raw["x_batch"], dtype=np.float32)
    z_flat = np.asarray(raw["z_batch_flat"], dtype=np.float32)
    n = len(legal)
    if n == 0:
        z_batch = np.zeros((0, HISTORY_LEN, CARD_DIM), dtype=np.float32)
    else:
        z_batch = z_flat.reshape(n, HISTORY_LEN, CARD_DIM)

    return {
        "position": int(raw["position"]),
        "legal_actions": legal,
        "x_no_action": x_no,
        "z": z,
        "x_batch": x_batch,
        "z_batch": z_batch,
        "phase": raw["phase"],
    }


class RustThullaEnv:
    """
    Drop-in API matching ThullaEnv for DMC self-play, backed by thulla_rust.

    reset()/step() return the same obs keys as the Python env.
    """

    def __init__(self, num_players: int = 4):
        if not RUST_AVAILABLE:
            raise RuntimeError("thulla_rust extension not installed")
        if num_players != 4:
            raise ValueError("Rust env supports exactly 4 players")
        self.num_players = num_players
        self._env = _RustEnvNative()
        self._last_obs: dict[str, Any] | None = None
        # Compatibility attrs used by some callers
        self.phase = "play"
        self.play_history: list[Card] = []

    def reset(self, seed: int | None = None) -> dict[str, Any]:
        seed_u = int(seed if seed is not None else 0)
        raw = self._env.reset(seed_u)
        self._last_obs = _reshape_rust_obs(raw)
        self.phase = self._last_obs["phase"]
        return self._last_obs

    def reset_hands(self, hands: list[list[Card]], ace_holder: int) -> dict[str, Any]:
        codes = [[c.code() for c in h] for h in hands]
        raw = self._env.reset_hands(codes, ace_holder)
        self._last_obs = _reshape_rust_obs(raw)
        self.phase = self._last_obs["phase"]
        return self._last_obs

    @property
    def current_seat(self) -> int:
        return int(self._env.current_seat())

    def legal_actions(self) -> list[Action]:
        if self._last_obs is None:
            return []
        return list(self._last_obs["legal_actions"])

    def step(self, action: Action):
        code = _action_to_code(action)
        out = self._env.step(code)
        done = bool(out["done"])
        rewards = np.asarray(out["rewards"], dtype=np.float32)
        if done or out["obs"] is None:
            self._last_obs = None
            return None, rewards, True, {"finish": True}
        self._last_obs = _reshape_rust_obs(out["obs"])
        self.phase = self._last_obs["phase"]
        return self._last_obs, rewards, False, {"phase": self.phase}

    def encode_played_action(self, action: Action) -> np.ndarray:
        return encode_action(action)


def make_env(prefer_rust: bool = True):
    """Factory: Rust when available (and prefer_rust), else Python ThullaEnv."""
    if prefer_rust and RUST_AVAILABLE:
        return RustThullaEnv()
    return ThullaEnv()
