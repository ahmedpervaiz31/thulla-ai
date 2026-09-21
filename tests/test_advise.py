import unittest

from thulla.advise import advise_session
from thulla.cards import Card, valid_moves
from thulla.players import choose_computer_card
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

    def test_advise_play_matches_bot_on_forced_first_trick(self):
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
        advice = advise_session(session)
        g = session.game
        seat = session.human_seat
        hand = list(g.players[seat].hand)
        expected = g.expected_for_seat(session.trick, seat)
        moves = valid_moves(hand, expected)
        view = g.view_for_seat(session.trick, seat)
        bot_card = choose_computer_card(hand, moves, expected, view)
        self.assertEqual(advice["recommended"]["card"], bot_card.code())

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

    def test_advise_pending_works_for_cpu_seat(self):
        from thulla.advise import advise_pending

        session = GameSession("human", 3, deal=False)
        session.game.set_hands(
            [
                [C("9", "Heart"), C("2", "Club")],
                [C("A", "Spade"), C("3", "Spade"), C("8", "Heart")],
                [C("5", "Spade"), C("6", "Club"), C("7", "Heart")],
            ],
            ace_spades_holder_idx=1,
        )
        session.leader = 1
        session._start_trick(first_trick=True)
        self.assertFalse(session.is_human(session.pending["seat"]))
        data = advise_pending(session)
        self.assertTrue(data["available"])
        self.assertEqual(data["action"], "play")
        self.assertEqual(data["recommended"]["card"], "AS")
        self.assertTrue(any(s["label"] == "RECOMMEND" for s in data["steps"]))

    def test_cpu_play_logs_advice(self):
        session = GameSession("ai", 3, deal=False)
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
        session.step()
        play = session._review_trick["plays"][0]
        self.assertFalse(play["human"])
        self.assertIn("advice", play)
        self.assertTrue(play["advice"]["steps"])
        self.assertEqual(play["advice"]["recommended"]["card"], play["card"])


if __name__ == "__main__":
    unittest.main()
