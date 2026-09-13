import io
import unittest
from unittest.mock import patch

from thulla.cards import Card, parse_card, valid_moves, cards_of_suit
from thulla.game import ThullaGame
from thulla.players import HumanPlayer, ScriptedPlayer
from main import parse_player_count


def C(number, colour):
    return Card(number, colour)


class ParseCardTests(unittest.TestCase):
    def test_compact_and_words(self):
        self.assertEqual(parse_card("AH").code(), "AH")
        self.assertEqual(str(C("10", "Spade")), "10S")
        self.assertEqual(parse_card("10S"), C("10", "Spade"))
        self.assertEqual(parse_card("Q hearts"), C("Q", "Heart"))
        self.assertEqual(parse_card("kd"), C("K", "Diamond"))
        self.assertIsNone(parse_card("nope"))


class ValidMovesTests(unittest.TestCase):
    def test_must_follow_suit_when_holding_it(self):
        hand = [C("2", "Heart"), C("A", "Spade")]
        moves = valid_moves(hand, cards_of_suit("Spade"))
        self.assertEqual(moves, [C("A", "Spade")])

    def test_any_card_when_void(self):
        hand = [C("2", "Heart"), C("3", "Diamond")]
        moves = valid_moves(hand, cards_of_suit("Spade"))
        self.assertEqual(moves, hand)

    def test_any_card_on_lead(self):
        hand = [C("2", "Heart"), C("A", "Spade")]
        self.assertEqual(valid_moves(hand, None), hand)


class HumanIllegalPlayTests(unittest.TestCase):
    def test_rejects_off_suit_then_accepts_follow(self):
        human = HumanPlayer("You")
        human.receive_cards([C("2", "Heart"), C("3", "Spade")])
        expected = cards_of_suit("Spade")
        with patch("builtins.input", side_effect=["2H", "3S"]), patch("sys.stdout", new=io.StringIO()):
            played = human.play_turn(expected)
        self.assertEqual(played, C("3", "Spade"))
        self.assertEqual(human.hand, [C("2", "Heart")])


class FirstTrickTests(unittest.TestCase):
    def test_ace_forced_off_suit_allowed_no_pickup_ace_leads_next(self):
        players = [ScriptedPlayer(f"P{i}") for i in range(4)]
        players[0].queue_plays([C("A", "Spade")])
        players[1].queue_plays([C("2", "Spade")])
        players[2].queue_plays([C("K", "Heart")])  # void in spades
        players[3].queue_plays([C("3", "Spade")])

        game = ThullaGame(players, verbose=False)
        game.set_hands(
            [
                [C("A", "Spade"), C("9", "Club")],
                [C("2", "Spade"), C("8", "Club")],
                [C("K", "Heart"), C("7", "Club")],
                [C("3", "Spade"), C("6", "Club")],
            ],
            ace_spades_holder_idx=0,
        )
        next_leader = game.resolve_trick(0, first_trick=True)
        self.assertEqual(next_leader, 0)
        self.assertEqual(len(players[0].hand), 1)
        self.assertEqual(len(players[2].hand), 1)
        self.assertNotIn(C("K", "Heart"), players[0].hand)
        self.assertNotIn(C("K", "Heart"), players[2].hand)


class ThullaPickupTests(unittest.TestCase):
    def test_thulla_stops_later_seats_highest_led_suit_picks_up(self):
        players = [ScriptedPlayer(f"P{i}") for i in range(4)]
        players[0].queue_plays([C("2", "Heart")])
        players[1].queue_plays([C("9", "Heart")])
        players[2].queue_plays([C("K", "Spade")])
        players[3].queue_plays([C("A", "Heart")])  # must not be consumed

        game = ThullaGame(players, verbose=False)
        game.set_hands(
            [
                [C("2", "Heart"), C("4", "Club")],
                [C("9", "Heart"), C("5", "Club")],
                [C("K", "Spade"), C("6", "Club")],
                [C("A", "Heart"), C("7", "Club")],
            ]
        )
        next_leader = game.resolve_trick(0, first_trick=False)
        self.assertEqual(next_leader, 1)
        self.assertEqual(len(players[3].hand), 2)
        self.assertIn(C("2", "Heart"), players[1].hand)
        self.assertIn(C("9", "Heart"), players[1].hand)
        self.assertIn(C("K", "Spade"), players[1].hand)
        self.assertEqual(len(players[0].hand), 1)
        self.assertEqual(len(players[2].hand), 1)


class GoOutWithPowerTests(unittest.TestCase):
    def test_empty_hand_gets_away_even_if_won_trick_lead_passes(self):
        players = [ScriptedPlayer(f"P{i}") for i in range(3)]
        players[0].queue_plays([C("A", "Heart")])
        players[1].queue_plays([C("2", "Heart")])
        players[2].queue_plays([C("3", "Heart")])

        game = ThullaGame(players, verbose=False)
        game.set_hands(
            [
                [C("A", "Heart")],
                [C("2", "Heart"), C("9", "Club")],
                [C("3", "Heart"), C("8", "Club")],
            ]
        )
        leader = game.resolve_trick(0, first_trick=False)
        self.assertEqual(leader, 0)
        leader = game.check_got_away(leader)
        self.assertEqual(game.winners, [players[0]])
        self.assertEqual(leader, 1)
        self.assertEqual(game.active_player_indices, [1, 2])


class NeighborTakeTests(unittest.TestCase):
    def test_take_next_clockwise_they_get_away_taker_still_leads(self):
        p0 = ScriptedPlayer("P0", take_decisions=[True])
        p1 = ScriptedPlayer("P1")
        p2 = ScriptedPlayer("P2")
        game = ThullaGame([p0, p1, p2], verbose=False)
        game.set_hands(
            [
                [C("A", "Heart"), C("2", "Club")],
                [C("3", "Spade"), C("4", "Diamond")],
                [C("5", "Club"), C("6", "Club")],
            ]
        )
        leader = game.take_phase(0)
        self.assertEqual(leader, 0)
        self.assertEqual(game.winners, [p1])
        self.assertIn(C("3", "Spade"), p0.hand)
        self.assertIn(C("4", "Diamond"), p0.hand)
        self.assertEqual(p1.hand, [])
        self.assertEqual(game.active_player_indices, [0, 2])
        self.assertEqual(game.next_active(0), 2)

    def test_victim_can_refuse_give(self):
        p0 = ScriptedPlayer("P0", take_decisions=[True])
        p1 = ScriptedPlayer("P1", give_decisions=[False])
        p2 = ScriptedPlayer("P2")
        game = ThullaGame([p0, p1, p2], verbose=False)
        game.set_hands(
            [
                [C("A", "Heart"), C("2", "Club")],
                [C("3", "Spade"), C("4", "Diamond")],
                [C("5", "Club"), C("6", "Club")],
            ]
        )
        leader = game.take_phase(0)
        self.assertEqual(leader, 0)
        self.assertEqual(game.winners, [])
        self.assertEqual(len(p0.hand), 2)
        self.assertEqual(len(p1.hand), 2)
        self.assertEqual(game.active_player_indices, [0, 1, 2])

    def test_heads_up_take_disabled(self):
        p0 = ScriptedPlayer("P0", take_decisions=[True])
        p1 = ScriptedPlayer("P1")
        game = ThullaGame([p0, p1], verbose=False)
        game.set_hands(
            [
                [C("A", "Heart"), C("2", "Club")],
                [C("3", "Spade"), C("4", "Diamond")],
            ]
        )
        self.assertIsNone(game.take_offer_context(0, 0))
        leader = game.take_phase(0)
        self.assertEqual(leader, 0)
        self.assertEqual(game.winners, [])
        self.assertEqual(len(p0.hand), 2)
        self.assertEqual(len(p1.hand), 2)
        self.assertEqual(game.active_player_indices, [0, 1])


class PlayerCountTests(unittest.TestCase):
    def test_flag_and_bounds(self):
        self.assertEqual(parse_player_count(["-p", "6"]), 6)
        with self.assertRaises(SystemExit):
            parse_player_count(["-p", "2"])
        with self.assertRaises(SystemExit):
            parse_player_count(["-p", "9"])


if __name__ == "__main__":
    unittest.main()
