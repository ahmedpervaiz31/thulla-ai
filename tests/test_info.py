import unittest

from thulla.cards import Card, cards_of_suit
from thulla.game import ThullaGame
from thulla.info import PublicInfo
from thulla.players import ComputerPlayer, ScriptedPlayer


def C(number, colour):
    return Card(number, colour)


class PublicInfoBookkeepingTests(unittest.TestCase):
    def test_first_trick_off_suit_is_void_and_discarded(self):
        players = [ScriptedPlayer(f"P{i}") for i in range(4)]
        players[0].queue_plays([C("A", "Spade")])
        players[1].queue_plays([C("2", "Spade")])
        players[2].queue_plays([C("K", "Heart")])
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
        game.resolve_trick(0, first_trick=True)

        self.assertIn("Spade", game.info.voids[2])
        discarded = game.info.discarded
        for card in (C("A", "Spade"), C("2", "Spade"), C("K", "Heart"), C("3", "Spade")):
            self.assertIn(card, discarded)
        for holdings in game.info.known_holdings.values():
            self.assertFalse(holdings)

    def test_thulla_records_void_and_known_pickup_not_discard(self):
        players = [ScriptedPlayer(f"P{i}") for i in range(4)]
        players[0].queue_plays([C("2", "Heart")])
        players[1].queue_plays([C("9", "Heart")])
        players[2].queue_plays([C("K", "Spade")])
        game = ThullaGame(players, verbose=False)
        game.set_hands(
            [
                [C("2", "Heart"), C("4", "Club")],
                [C("9", "Heart"), C("5", "Club")],
                [C("K", "Spade"), C("6", "Club")],
                [C("A", "Heart"), C("7", "Club")],
            ]
        )
        game.resolve_trick(0, first_trick=False)

        self.assertIn("Heart", game.info.voids[2])
        known = game.info.known_holdings[1]
        self.assertEqual(known, {C("2", "Heart"), C("9", "Heart"), C("K", "Spade")})
        self.assertNotIn(C("2", "Heart"), game.info.discarded)
        self.assertNotIn("Heart", game.info.voids[1])
        self.assertNotIn("Spade", game.info.voids[1])


class PlayHistoryInferenceTests(unittest.TestCase):
    def test_tracks_who_played_and_under_ceiling(self):
        info = PublicInfo(3)
        info.hand_sizes = [5, 5, 5]

        info.note_play(0, C("9", "Spade"), None)
        self.assertEqual(info.played_by[0], [C("9", "Spade")])
        self.assertEqual(info.highest_played[0]["Spade"], C("9", "Spade"))

        # Seat 1 ducks under the 9 with a 5 → soft hint of no 6/7/8 Spades.
        info.note_play(1, C("5", "Spade"), "Spade")
        self.assertEqual(info.played_by[1], [C("5", "Spade")])
        self.assertEqual(info.under_ceilings[1]["Spade"], (C("5", "Spade"), C("9", "Spade")))

        view = info.view_for(2, [])
        # Soft only — voids are hard; duck gaps are not proofs.
        self.assertFalse(view.cannot_hold(1, C("7", "Spade")))
        self.assertTrue(view.unlikely_hold(1, C("7", "Spade")))
        self.assertFalse(view.unlikely_hold(1, C("4", "Spade")))
        self.assertFalse(view.unlikely_hold(1, C("A", "Spade")))
        self.assertEqual(view.cards_played_by(0), [C("9", "Spade")])
        self.assertEqual(
            view.duck_gap_unknowns(1, "Spade"),
            [C("6", "Spade"), C("7", "Spade"), C("8", "Spade")],
        )

    def test_duck_gap_ignores_already_public_cards(self):
        """A, K, Q on one trick: Q-under-A must not soft-hint K/A (already public)."""
        info = PublicInfo(3)
        info.hand_sizes = [5, 5, 5]
        info.note_play(0, C("A", "Spade"), None)
        info.note_play(1, C("K", "Spade"), "Spade")
        info.note_play(2, C("Q", "Spade"), "Spade")
        # Still in the trick (not discarded yet) — but publicly located.
        self.assertEqual(info.under_ceilings[2]["Spade"], (C("Q", "Spade"), C("A", "Spade")))
        view = info.view_for(0, [])
        self.assertEqual(view.duck_gap_unknowns(2, "Spade"), [])
        self.assertFalse(view.unlikely_hold(2, C("K", "Spade")))
        self.assertFalse(view.unlikely_hold(2, C("A", "Spade")))
        # After clean discard, still nothing live in the Q–A gap.
        info.finish_clean(list(info.trick_cards))
        view = info.view_for(0, [])
        self.assertEqual(view.duck_gap_unknowns(2, "Spade"), [])
        self.assertFalse(view.unlikely_hold(2, C("K", "Spade")))

    def test_take_lead_marks_suit_high(self):
        info = PublicInfo(2)
        info.hand_sizes = [3, 3]
        info.note_play(0, C("8", "Heart"), None)
        info.note_play(1, C("K", "Heart"), "Heart")
        self.assertEqual(info.suit_high_shown[1]["Heart"], C("K", "Heart"))
        view = info.view_for(0, [])
        self.assertFalse(view.cannot_hold(1, C("A", "Heart")))
        self.assertTrue(view.unlikely_hold(1, C("A", "Heart")))
        self.assertFalse(view.unlikely_hold(1, C("9", "Heart")))


class BotPolicyTests(unittest.TestCase):
    def test_does_not_lead_suit_next_player_is_void_in(self):
        info = PublicInfo(3)
        info.voids[1].add("Heart")
        view = info.view_for(0, [1, 2])
        bot = ComputerPlayer("CPU")
        bot.receive_cards([C("2", "Heart"), C("3", "Club")])
        played = bot.play_turn(None, view)
        self.assertEqual(played, C("3", "Club"))

    def test_follow_ducks_with_highest_under_current(self):
        info = PublicInfo(3)
        info.current_highest = C("9", "Spade")
        info.current_highest_player = 0
        info.led_suit = "Spade"
        info.voids[2].add("Spade")
        view = info.view_for(1, [2])
        bot = ComputerPlayer("CPU")
        bot.receive_cards([C("2", "Spade"), C("8", "Spade")])
        played = bot.play_turn(cards_of_suit("Spade"), view)
        self.assertEqual(played, C("8", "Spade"))

    def test_thulla_prefers_suit_victim_is_void_in(self):
        info = PublicInfo(2)
        info.current_highest = C("9", "Heart")
        info.current_highest_player = 0
        info.led_suit = "Heart"
        info.voids[0].add("Club")
        view = info.view_for(1, [])
        bot = ComputerPlayer("CPU")
        bot.receive_cards([C("5", "Club"), C("A", "Diamond")])
        played = bot.play_turn(cards_of_suit("Heart"), view)
        self.assertEqual(played, C("5", "Club"))


class HeadsUpCompleteInfoTests(unittest.TestCase):
    def test_deduces_opponent_hand_from_discards_and_mine(self):
        from thulla.cards import create_deck

        info = PublicInfo(3)
        info.active_indices = [0, 1]
        me = [C("2", "Heart"), C("3", "Heart"), C("4", "Club")]
        opp = [C("5", "Spade"), C("6", "Diamond")]
        # Everything else discarded (or known empty seats).
        rest = [
            c
            for c in create_deck()
            if c not in me and c not in opp
        ]
        info.discarded = set(rest)
        info.hand_sizes = [3, 2, 0]
        view = info.view_for(0, [1])
        deduced = view.deduced_hand(1, me)
        self.assertEqual(deduced, set(opp))
        self.assertEqual(view.unknown_slots(1, me), 0)
        self.assertEqual(view.free_cards(me), [])
        self.assertEqual(view.visible_cards(1, me), set(opp))

    def test_no_deduction_with_three_active(self):
        from thulla.cards import create_deck

        info = PublicInfo(3)
        info.active_indices = [0, 1, 2]
        me = [C("2", "Heart")]
        info.discarded = set(create_deck()) - set(me) - {
            C("3", "Club"),
            C("4", "Club"),
            C("5", "Club"),
        }
        info.hand_sizes = [1, 2, 1]
        view = info.view_for(0, [1, 2])
        self.assertIsNone(view.deduced_hand(1, me))
        self.assertGreater(len(view.free_cards(me)), 0)


if __name__ == "__main__":
    unittest.main()
