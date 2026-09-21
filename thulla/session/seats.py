"""Human seat for the web Interactive GameSession."""

from __future__ import annotations

from ..players import BasePlayer


class InteractiveSeat(BasePlayer):
    """Human seat for the web session — never calls input()."""

    def play_turn(self, expected_cards, view=None):
        raise RuntimeError("InteractiveSeat must not be driven via play_turn; use GameSession")

    def offer_take(self, target_name, n_cards, view=None, neighbor_idx=None, i_am_leader=False):
        raise RuntimeError("InteractiveSeat must not be driven via offer_take; use GameSession")

    def offer_give(self, asker_name, n_cards, view=None, asker_idx=None):
        raise RuntimeError("InteractiveSeat must not be driven via offer_give; use GameSession")
