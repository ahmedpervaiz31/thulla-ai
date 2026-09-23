"""App bot wiring: non-4-player tables stay on the heuristic."""

from __future__ import annotations

import unittest

from thulla.players import ComputerPlayer
from thulla.session import GameSession
from thulla.session.core import _make_cpu


class MakeAppBotWiringTests(unittest.TestCase):
    def test_non_four_uses_heuristic(self):
        bot = _make_cpu("CPU1", 3)
        self.assertIsInstance(bot, ComputerPlayer)
        self.assertEqual(bot.name, "CPU1")

    def test_session_exposes_bot_kind(self):
        session = GameSession("human", 3, deal=False)
        self.assertEqual(session.bot_kind, "heuristic")
        state = session.to_dict()
        self.assertEqual(state.get("bot_kind"), "heuristic")


if __name__ == "__main__":
    unittest.main()
