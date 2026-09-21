"""Step-based game session for the web UI (no blocking game_loop / input)."""

from .core import SESSIONS, GameSession, create_session, get_session
from .seats import InteractiveSeat

__all__ = [
    "GameSession",
    "InteractiveSeat",
    "SESSIONS",
    "create_session",
    "get_session",
]
