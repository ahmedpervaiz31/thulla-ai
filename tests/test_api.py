import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from thulla import persist
from thulla.session import SESSIONS
from web.app import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._root = Path(self._tmpdir.name)
        self._patcher = mock.patch.object(persist, "GAMES_ROOT", self._root)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        SESSIONS.clear()
        persist.ensure_games_layout()
        self.client = TestClient(app)

    def test_create_and_get_game(self):
        created = self.client.post(
            "/api/games", json={"mode": "human", "players": 4}
        )
        self.assertEqual(created.status_code, 200)
        body = created.json()
        self.assertIn("id", body)
        self.assertEqual(body["mode"], "human")

        loaded = self.client.get(f"/api/games/{body['id']}")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["id"], body["id"])

    def test_step_cpu_after_create(self):
        created = self.client.post(
            "/api/games", json={"mode": "human", "players": 4}
        )
        self.assertEqual(created.status_code, 200)
        body = created.json()
        game_id = body["id"]
        # Deal may give AS to the human (seat 0). Play first so /step has a CPU turn.
        pending = body.get("pending") or {}
        if pending.get("type") == "play" and pending.get("seat") == 0:
            card = pending["legal"][0]
            played = self.client.post(
                f"/api/games/{game_id}/play", json={"card": card}
            )
            self.assertEqual(played.status_code, 200)
        stepped = self.client.post(f"/api/games/{game_id}/step", json={})
        self.assertEqual(stepped.status_code, 200)
        self.assertIsNotNone(stepped.json().get("pending"))


if __name__ == "__main__":
    unittest.main()
