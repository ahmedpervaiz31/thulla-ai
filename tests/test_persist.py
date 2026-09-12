"""Persistence round-trip for web sessions."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from thulla.cards import Card
from thulla import persist
from thulla.session import GameSession, SESSIONS, create_session


def C(number, colour):
    return Card(number, colour)


class PersistRoundTripTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._root = Path(self._tmpdir.name)
        self._patcher = mock.patch.object(persist, "GAMES_ROOT", self._root)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        SESSIONS.clear()

    def test_save_and_reload_human_game(self):
        session = create_session("human", 4)
        gid = session.id
        persist.save_session(session)

        folder = self._root / "human_vs_ai"
        self.assertTrue((folder / f"{gid}.json").is_file())

        SESSIONS.clear()
        loaded = persist.get_or_load_session(gid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, gid)
        self.assertEqual(loaded.mode, "human")
        self.assertEqual(len(loaded.game.players), 4)
        self.assertEqual(
            [len(p.hand) for p in loaded.game.players],
            [len(p.hand) for p in session.game.players],
        )

    def test_ai_mode_folder(self):
        session = create_session("ai", 3)
        persist.save_session(session)
        self.assertTrue((self._root / "ai_vs_ai" / f"{session.id}.json").is_file())


if __name__ == "__main__":
    unittest.main()
