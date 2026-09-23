"""DMC policy player + shared checkpoint load for the web app / eval."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import torch

from thulla.cards import valid_moves
from thulla.players import BasePlayer, ComputerPlayer

from .encode import ASK, PASS, build_action_batch, encode_state
from .models import Model

log = logging.getLogger("thulla_dmc")

# DMC obs / net assumes fixed 4 seats (see encode.NUM_PLAYERS).
DMC_PLAYER_COUNT = 4

_REPO_ROOT = Path(__file__).resolve().parent.parent
_shared_model: Model | None = None
_shared_path: Path | None = None
_load_attempted = False
_load_error: str | None = None


def checkpoint_candidates() -> list[Path]:
    """Search order for model_best (prefer best-vs-heuristic over latest)."""
    paths: list[Path] = []
    env = os.environ.get("THULLA_DMC_CHECKPOINT")
    if env:
        paths.append(Path(env).expanduser())
    # Workspace root (parent of thulla-ai) and package root are common drop spots.
    workspace_root = _REPO_ROOT.parent
    paths.extend(
        [
            _REPO_ROOT / "model_best.tar",
            workspace_root / "model_best.tar",
            _REPO_ROOT / "checkpoints" / "model_best.tar",
            _REPO_ROOT / "thulla_dmc_checkpoints" / "thulla_dmc" / "model_best.tar",
            _REPO_ROOT / "model.tar",
            workspace_root / "model.tar",
            _REPO_ROOT / "checkpoints" / "model.tar",
            _REPO_ROOT / "thulla_dmc_checkpoints" / "thulla_dmc" / "model.tar",
        ]
    )
    return paths


def resolve_checkpoint() -> Path | None:
    for path in checkpoint_candidates():
        if path.is_file():
            return path
    return None


def load_model(checkpoint: str | Path | None = None, device: str = "cpu") -> Model:
    """Load a Model from a .tar checkpoint (model_state_dict or raw state_dict)."""
    path = Path(checkpoint) if checkpoint else resolve_checkpoint()
    if path is None or not path.is_file():
        raise FileNotFoundError(
            "No DMC checkpoint found. Copy model_best.tar to "
            f"{_REPO_ROOT / 'checkpoints' / 'model_best.tar'} "
            "or set THULLA_DMC_CHECKPOINT."
        )
    dev = torch.device(
        device if device != "cpu" and torch.cuda.is_available() else "cpu"
    )
    model = Model(device="cpu" if dev.type == "cpu" else device)
    try:
        state = torch.load(path, map_location=dev, weights_only=False)
    except TypeError:
        state = torch.load(path, map_location=dev)
    if isinstance(state, dict) and "model_state_dict" in state:
        model.load_state_dict(state["model_state_dict"])
    else:
        model.load_state_dict(state)
    if dev.type != "cpu":
        # App / eval scoring stays on CPU for simplicity.
        cpu = Model(device="cpu")
        cpu.load_state_dict({k: v.detach().cpu() for k, v in model.state_dict().items()})
        model = cpu
    model.eval()
    return model


def get_shared_model() -> Model | None:
    """Lazy singleton for the web app. Returns None if unavailable."""
    global _shared_model, _shared_path, _load_attempted, _load_error
    if _shared_model is not None:
        return _shared_model
    if _load_attempted:
        return None
    _load_attempted = True
    path = resolve_checkpoint()
    if path is None:
        _load_error = "no checkpoint file"
        log.warning(
            "DMC bot disabled: no model_best.tar "
            "(place under checkpoints/ or set THULLA_DMC_CHECKPOINT)"
        )
        return None
    try:
        _shared_model = load_model(path)
        _shared_path = path
        log.info("DMC bot loaded from %s", path)
    except Exception as exc:  # noqa: BLE001 — app must fall back to heuristic
        _load_error = str(exc)
        log.warning("DMC bot disabled: failed to load %s (%s)", path, exc)
        _shared_model = None
    return _shared_model


def dmc_status() -> dict:
    """Diagnostics for logs / optional API surfacing."""
    get_shared_model()
    return {
        "active": _shared_model is not None,
        "checkpoint": str(_shared_path) if _shared_path else None,
        "error": _load_error,
    }


def make_app_bot(name: str, player_count: int) -> BasePlayer:
    """
    App CPU seat: DMC when 4 players + checkpoint available, else ComputerPlayer.
    """
    if player_count != DMC_PLAYER_COUNT:
        return ComputerPlayer(name)
    model = get_shared_model()
    if model is None:
        return ComputerPlayer(name)
    return DMCPlayer(name, model, torch.device("cpu"))


class DMCPlayer(BasePlayer):
    """Greedy DMC policy (card play + ASK/PASS). Victims always give."""

    def __init__(self, name, model: Model, device: torch.device | None = None):
        super().__init__(name)
        self.model = model
        self.device = device or torch.device("cpu")
        self.play_history: list = []
        self.game = None

    def bind(self, game, play_history: list):
        """Attach live game + shared chronological play list (session-owned)."""
        self.game = game
        self.play_history = play_history

    def reset_history(self):
        self.play_history = []

    def note_played(self, card):
        self.play_history.append(card)

    def play_turn(self, expected_cards, view=None):
        raise RuntimeError("DMCPlayer uses select_card()/choose() via session or eval")

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
        x_batch, _z_batch = build_action_batch(x_no, z, legal)
        # Pass single-state z (2D): model runs LSTM once, then scores all actions.
        z_t = torch.from_numpy(np.ascontiguousarray(z)).float().to(self.device)
        x_t = torch.from_numpy(np.ascontiguousarray(x_batch)).float().to(self.device)
        with torch.inference_mode():
            out = self.model.forward(z_t, x_t, exp_epsilon=0.0)
        idx = int(out["action"].detach().cpu().item())
        return legal[idx]

    def select_card(self, game, trick, expected_cards):
        """Pick a legal card without removing it (session apply_play removes)."""
        self.game = game
        legal = valid_moves(self.hand, expected_cards)
        return self._pick(legal, trick=trick, take_phase=False)

    def choose(self, game, trick, expected_cards):
        """Eval harness: select and remove from hand."""
        card = self.select_card(game, trick, expected_cards)
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
