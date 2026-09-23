"""Minimal DouZero-style Deep Monte Carlo trainer for Thulla."""

__all__ = ["train", "DMCPlayer", "load_model", "make_app_bot"]


def __getattr__(name):
    if name == "train":
        from .train import train

        return train
    if name == "DMCPlayer":
        from .player import DMCPlayer

        return DMCPlayer
    if name == "load_model":
        from .player import load_model

        return load_model
    if name == "make_app_bot":
        from .player import make_app_bot

        return make_app_bot
    raise AttributeError(name)
