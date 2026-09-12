import unittest

from thulla.advise import advise_session
from thulla.cards import Card
from thulla.session import GameSession


def C(number, colour):
    return Card(number, colour)


class AdviseTests(unittest.TestCase):
    def test_ai_mode_unavailable(self):
        session = GameSession("ai", 3)
        data = advise_session(session)
        self.assertFalse(data["available"])

    def test_human_play_advice_has_steps(self):
        session = GameSession("human", 3, deal=False)
        session.game.set_hands(
            [
                [C("A", "Spade"), C("9", "Heart"), C("2", "Club")],
                [C("3", "Spade"), C("8", "Heart"), C("4", "Club")],
                [C("5", "Spade"), C("7", "Heart"), C("6", "Club")],
            ],
            ace_spades_holder_idx=0,
        )
        session.leader = 0
        session._start_trick(first_trick=True)
        data = advise_session(session)
        self.assertTrue(data["available"])
        self.assertEqual(data["action"], "play")
        # First trick forces AS — treated as follow of the ace expectation.
        self.assertIn(data["kind"], ("lead", "follow"))
        self.assertEqual(data["recommended"]["type"], "play")
        self.assertEqual(data["recommended"]["card"], "AS")
        self.assertTrue(any(s["label"] == "RECOMMEND" for s in data["steps"]))

    def test_human_free_lead_advice(self):
        session = GameSession("human", 3, deal=False)
        session.game.set_hands(
            [
                [C("9", "Heart"), C("2", "Club"), C("K", "Diamond")],
                [C("3", "Spade"), C("8", "Heart"), C("4", "Club")],
                [C("5", "Spade"), C("7", "Heart"), C("6", "Club")],
            ]
        )
        session.leader = 0
        session._start_trick(first_trick=False)
        data = advise_session(session)
        self.assertTrue(data["available"])
        self.assertEqual(data["kind"], "lead")
        self.assertEqual(data["recommended"]["type"], "play")
        self.assertIn(data["recommended"]["card"], {"9H", "2C", "KD"})
        self.assertTrue(data.get("suit_risks"))

    def test_not_your_turn(self):
        session = GameSession("human", 3, deal=False)
        session.game.set_hands(
            [
                [C("9", "Heart"), C("2", "Club")],
                [C("A", "Spade"), C("3", "Spade")],
                [C("5", "Spade"), C("6", "Club")],
            ],
            ace_spades_holder_idx=1,
        )
        session.leader = 1
        session._start_trick(first_trick=True)
        data = advise_session(session)
        self.assertFalse(data["available"])
        self.assertIn("Not your turn", data["reason"])


if __name__ == "__main__":
    unittest.main()
