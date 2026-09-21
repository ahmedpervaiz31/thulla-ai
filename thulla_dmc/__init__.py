"""Minimal DouZero-style Deep Monte Carlo trainer for Thulla."""

__all__ = ["train"]


def __getattr__(name):
    if name == "train":
        from .train import train

        return train
    raise AttributeError(name)
