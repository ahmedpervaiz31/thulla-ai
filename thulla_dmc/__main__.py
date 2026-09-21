"""CLI entry: python -m thulla_dmc.train ..."""

from .arguments import parse_args
from .train import train

if __name__ == "__main__":
    train(parse_args())
