"""Replay completed-game JSON into review frames."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from thulla import persist
from thulla.session import SESSIONS, create_session
from thulla.ui_frames import frames_from_session, rebuild_frames_from_review


class UiFramesTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._root = Path(self._tmpdir.name)
        self._patcher = mock.patch.object(persist, "GAMES_ROOT", self._root)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        SESSIONS.clear()
        persist.ensure_games_layout()

    def test_list_and_review_after_finish(self):
        session = create_session("human", 3)
        session._finish_game()
        persist.save_session(session)

        games = persist.list_saved_games("completed")
        self.assertTrue(any(g["id"] == session.id for g in games))
        entry = next(g for g in games if g["id"] == session.id)
        self.assertTrue(entry["reviewable"])

        review = persist.get_review_for_game(session.id)
        self.assertIsNotNone(review)
        self.assertGreaterEqual(review["frame_count"], 1)
        self.assertTrue(
            any(isinstance(s.get("hand"), list) for s in review["frames"][0]["seats"])
        )

    def test_rebuild_from_opening_only(self):
        session = create_session("ai", 3)
        opening = session.review["opening_hands"]
        payload = {
            "id": session.id,
            "mode": "ai",
            "players": [p.name for p in session.game.players],
            "opening_hands": opening,
            "tricks": [],
            "takes": [],
        }
        frames = rebuild_frames_from_review(payload)
        self.assertGreaterEqual(len(frames), 1)
        self.assertEqual(frames[0]["mode"], "ai")
        self.assertIn("public_info", frames[0])
        self.assertTrue(isinstance(frames[0]["seats"][0].get("hand"), list))

    def test_rebuild_played_ai_game_has_hands(self):
        session = create_session("ai", 3)
        persist.persist_and_return(session)
        guard = 0
        while session.phase != "finished" and guard < 400:
            session.step()
            persist.persist_and_return(session)
            guard += 1
        self.assertEqual(session.phase, "finished")

        frames = frames_from_session(session)
        self.assertGreater(len(frames), 5)
        mid = frames[min(10, len(frames) - 1)]
        for seat in mid["seats"]:
            if seat.get("hand_size", 0) > 0:
                self.assertIsInstance(seat.get("hand"), list)
                self.assertGreater(len(seat["hand"]), 0)

        review = persist.get_review_for_game(session.id)
        self.assertIsNotNone(review)
        self.assertGreater(review["frame_count"], 5)
        self.assertTrue(review["frames"][-1].get("finished"))


if __name__ == "__main__":
    unittest.main()
