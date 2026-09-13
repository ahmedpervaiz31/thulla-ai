"""Persistence round-trip for web sessions."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from thulla.cards import Card
from thulla import persist
from thulla.session import SESSIONS, create_session


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
        persist.ensure_games_layout()

    def test_save_and_reload_human_game(self):
        session = create_session("human", 4)
        gid = session.id
        persist.save_session(session)

        folder = self._root / "ongoing" / "human_vs_ai"
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
        self.assertIsNotNone(loaded.review.get("opening_hands"))

    def test_ai_mode_folder(self):
        session = create_session("ai", 3)
        persist.save_session(session)
        self.assertTrue(
            (self._root / "ongoing" / "ai_vs_ai" / f"{session.id}.json").is_file()
        )

    def test_completed_export_on_finish(self):
        session = create_session("human", 3)
        # Force finish without playing.
        session._finish_game()
        path = persist.save_session(session)
        self.assertEqual(path.parent.name, "human_vs_ai")
        self.assertEqual(path.parent.parent.name, "completed")
        self.assertFalse(
            (self._root / "ongoing" / "human_vs_ai" / f"{session.id}.json").exists()
        )
        data = persist.load_checkpoint(path)
        self.assertEqual(data["version"], 2)
        self.assertIn("tricks", data)
        self.assertIn("result", data)
        self.assertNotIn("game", data)
        md = persist.completed_md_path(session.mode, session.id)
        self.assertTrue(md.is_file())
        text = md.read_text(encoding="utf-8")
        self.assertIn(session.id, text)


if __name__ == "__main__":
    unittest.main()
