"""Review log + completed markdown formatting."""

import unittest

from thulla.review import completed_markdown, compact_advice, new_review


class ReviewHelpersTests(unittest.TestCase):
    def test_compact_advice_drops_unavailable(self):
        self.assertIsNone(compact_advice({"available": False, "reason": "x"}))

    def test_compact_advice_keeps_steps(self):
        adv = compact_advice(
            {
                "available": True,
                "action": "play",
                "kind": "follow",
                "recommended": {"type": "play", "card": "9S"},
                "steps": [{"label": "POLICY", "detail": "soft duck"}],
                "situation": {"hand_size": 12},
            }
        )
        self.assertEqual(adv["recommended"]["card"], "9S")
        self.assertEqual(adv["steps"][0]["label"], "POLICY")
        self.assertNotIn("situation", adv)

    def test_markdown_includes_ideal_mismatch(self):
        payload = {
            "id": "abc",
            "mode": "human",
            "players": ["You", "CPU1"],
            "result": {
                "finishing_order": [{"place": 1, "seat": 0, "name": "You"}],
                "loser": {"seat": 1, "name": "CPU1"},
            },
            "opening_hands": [["AS", "2H"], ["KS"]],
            "tricks": [
                {
                    "n": 1,
                    "leader": "You",
                    "first_trick": True,
                    "plays": [
                        {
                            "name": "You",
                            "card": "10S",
                            "kind": "follow",
                            "hand_before": ["9S", "10S"],
                            "legal": ["9S", "10S"],
                            "advice": {
                                "recommended": {"type": "play", "card": "9S"},
                                "steps": [
                                    {"label": "RECOMMEND", "detail": "Play 9S"}
                                ],
                            },
                            "followed_advice": False,
                        }
                    ],
                    "result": "win",
                    "winner": "You",
                    "pot": ["AS", "10S"],
                }
            ],
            "takes": [
                {
                    "after_trick": 1,
                    "asker": "CPU1",
                    "target": "You",
                    "n_cards": 2,
                    "given": False,
                    "advice": {
                        "recommended": {"type": "take", "accept": False},
                        "steps": [
                            {"label": "POLICY", "detail": "Bot never asks"},
                            {"label": "RECOMMEND", "detail": "Decline"},
                        ],
                    },
                    "followed_advice": True,
                }
            ],
            "advice_requests": [],
        }
        md = completed_markdown(payload)
        self.assertIn("differed from Ideal", md)
        self.assertIn("Ideal: `9S`", md)
        self.assertIn("Opening hands", md)
        self.assertIn("Ideal: no ✓", md)
        self.assertIn("POLICY: Bot never asks", md)


if __name__ == "__main__":
    unittest.main()
