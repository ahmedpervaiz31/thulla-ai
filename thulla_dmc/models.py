"""Shared value network: score (state, action) pairs."""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from .encode import X_DIM, Z_DIM, Z_ROWS


class ThullaModel(nn.Module):
    def __init__(self, hidden: int = 256, lstm_hidden: int = 128):
        super().__init__()
        self.lstm = nn.LSTM(Z_DIM, lstm_hidden, batch_first=True)
        self.fc1 = nn.Linear(X_DIM + lstm_hidden, hidden)
        self.fc2 = nn.Linear(hidden, hidden)
        self.fc3 = nn.Linear(hidden, hidden)
        self.fc4 = nn.Linear(hidden, 1)

    def forward(self, z, x, return_value: bool = False, exp_epsilon: float = 0.0):
        """
        z: (B, Z_ROWS, Z_DIM) or (Z_ROWS, Z_DIM) when scoring one state's actions
        x: (B, X_DIM)
        """
        if z.dim() == 2:
            z = z.unsqueeze(0).expand(x.shape[0], -1, -1)
        lstm_out, _ = self.lstm(z)
        h = lstm_out[:, -1, :]
        h = torch.cat([h, x], dim=-1)
        h = torch.relu(self.fc1(h))
        h = torch.relu(self.fc2(h))
        h = torch.relu(self.fc3(h))
        values = self.fc4(h)
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

    def forward(self, z, x, return_value=False, exp_epsilon=0.0):
        return self.model(z, x, return_value=return_value, exp_epsilon=exp_epsilon)

    def get_model(self):
        return self.model
