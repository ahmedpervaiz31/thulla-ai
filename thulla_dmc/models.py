"""Shared value network: score (state, action) pairs."""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from .encode import X_DIM, Z_DIM


class ThullaModel(nn.Module):
    def __init__(self, hidden: int = 256, lstm_hidden: int = 128):
        super().__init__()
        self.lstm = nn.LSTM(Z_DIM, lstm_hidden, batch_first=True)
        self.fc1 = nn.Linear(X_DIM + lstm_hidden, hidden)
        self.fc2 = nn.Linear(hidden, hidden)
        self.fc3 = nn.Linear(hidden, hidden)
        self.fc4 = nn.Linear(hidden, 1)

    def _encode_state_actions(self, z, x, counts=None):
        """
        LSTM over history once per distinct state, then score each action row in x.

        z:
          - (Z_ROWS, Z_DIM): one state, x is (N_actions, X_DIM)
          - (S, Z_ROWS, Z_DIM) with counts: S states, x rows grouped by counts
          - (B, Z_ROWS, Z_DIM) without counts: one state per x row (learner path)
        """
        if counts is not None:
            if z.dim() != 3:
                raise ValueError("counts requires z shaped (S, Z_ROWS, Z_DIM)")
            if not torch.is_tensor(counts):
                counts = torch.as_tensor(counts, dtype=torch.long, device=z.device)
            else:
                counts = counts.to(device=z.device, dtype=torch.long)
            lstm_out, _ = self.lstm(z)
            h = lstm_out[:, -1, :]
            h = torch.repeat_interleave(h, counts, dim=0)
            if h.shape[0] != x.shape[0]:
                raise ValueError(
                    f"counts sum {h.shape[0]} != x batch {x.shape[0]}"
                )
        elif z.dim() == 2:
            # Single state, many actions — avoid repeating the LSTM over identical z.
            lstm_out, _ = self.lstm(z.unsqueeze(0))
            h = lstm_out[:, -1, :].expand(x.shape[0], -1)
        else:
            if z.dim() != 3:
                raise ValueError(f"expected z dim 2 or 3, got {z.dim()}")
            lstm_out, _ = self.lstm(z)
            h = lstm_out[:, -1, :]
        h = torch.cat([h, x], dim=-1)
        h = torch.relu(self.fc1(h))
        h = torch.relu(self.fc2(h))
        h = torch.relu(self.fc3(h))
        return self.fc4(h)

    def forward(
        self,
        z,
        x,
        return_value: bool = False,
        exp_epsilon: float = 0.0,
        counts=None,
    ):
        """
        z: (B, Z_ROWS, Z_DIM), (Z_ROWS, Z_DIM), or (S, Z_ROWS, Z_DIM) with counts
        x: (B, X_DIM)
        counts: optional LongTensor/list of action counts per state when z is (S, ...)
        """
        values = self._encode_state_actions(z, x, counts=counts)
        if return_value:
            return {"values": values}
        if exp_epsilon > 0 and np.random.rand() < exp_epsilon:
            action = torch.randint(values.shape[0], (1,))[0]
        else:
            action = torch.argmax(values, dim=0)[0]
        return {"action": action, "values": values}


class Model:
    """Thin wrapper matching DouZero's Model interface (single shared net)."""

    def __init__(self, device="cpu"):
        if device != "cpu":
            device = f"cuda:{device}"
        self.device = torch.device(device)
        self.model = ThullaModel().to(self.device)

    def share_memory(self):
        self.model.share_memory()

    def eval(self):
        self.model.eval()

    def train(self):
        self.model.train()

    def parameters(self):
        return self.model.parameters()

    def state_dict(self):
        return self.model.state_dict()

    def load_state_dict(self, state):
        self.model.load_state_dict(state)

    def forward(self, z, x, return_value=False, exp_epsilon=0.0, counts=None):
        return self.model(
            z, x, return_value=return_value, exp_epsilon=exp_epsilon, counts=counts
        )

    def get_model(self):
        return self.model
