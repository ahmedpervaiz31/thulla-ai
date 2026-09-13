import unittest

from thulla.cards import Card, cards_of_suit
from thulla.info import PublicInfo
from thulla.players import ComputerPlayer, should_cpu_take
from thulla.prob import case_a_should_take, estimate_lead_lose_rates, estimate_thulla_prob


def C(number, colour):
    return Card(number, colour)


class EstimateThullaProbTests(unittest.TestCase):
    def test_known_void_is_certain(self):
        info = PublicInfo(3)
        info.hand_sizes = [5, 5, 5]
        info.voids[2].add("Spade")
        view = info.view_for(1, [2])
        hand = [C("2", "Spade"), C("8", "Spade")]
        self.assertEqual(estimate_thulla_prob(view, "Spade", hand, [2]), 1.0)

    def test_fat_suit_one_seat_low_prob(self):
        info = PublicInfo(2)
        info.hand_sizes = [1, 12]
        view = info.view_for(0, [1])
        hand = [C("2", "Spade")]
        p = estimate_thulla_prob(view, "Spade", hand, [1], samples=100)
        self.assertLess(p, 0.25)

    def test_follow_takes_ace_when_dump_safe(self):
        info = PublicInfo(2)
        info.hand_sizes = [3, 12]
        info.current_highest = C("9", "Spade")
        info.current_highest_player = 1
        info.led_suit = "Spade"
        view = info.view_for(0, [])
        bot = ComputerPlayer("CPU")
        bot.receive_cards([C("2", "Spade"), C("8", "Spade"), C("A", "Spade")])
        info.hand_sizes[0] = 3
        played = bot.play_turn(cards_of_suit("Spade"), view)
        self.assertEqual(played, C("A", "Spade"))

    def test_follow_ducks_when_void_after(self):
        info = PublicInfo(3)
        info.hand_sizes = [5, 2, 5]
        info.current_highest = C("9", "Spade")
        info.current_highest_player = 0
        info.led_suit = "Spade"
        info.voids[2].add("Spade")
        view = info.view_for(1, [2])
        bot = ComputerPlayer("CPU")
        bot.receive_cards([C("2", "Spade"), C("8", "Spade")])
        played = bot.play_turn(cards_of_suit("Spade"), view)
        self.assertEqual(played, C("8", "Spade"))

    def test_lead_skips_suit_anyone_after_void_in(self):
        info = PublicInfo(3)
        info.hand_sizes = [2, 5, 5]
        info.voids[2].add("Heart")
        view = info.view_for(0, [1, 2])
        bot = ComputerPlayer("CPU")
        bot.receive_cards([C("2", "Heart"), C("3", "Club")])
        played = bot.play_turn(None, view)
        self.assertEqual(played, C("3", "Club"))

    def test_emptying_prefers_duck_over_ace_as_highest(self):
        info = PublicInfo(3)
        info.hand_sizes = [2, 5, 5]
        info.current_highest = C("9", "Spade")
        info.current_highest_player = 0
        info.led_suit = "Spade"
        info.voids[2].add("Spade")
        view = info.view_for(1, [2])
        bot = ComputerPlayer("CPU")
        bot.receive_cards([C("2", "Spade"), C("A", "Spade")])
        played = bot.play_turn(cards_of_suit("Spade"), view)
        self.assertEqual(played, C("2", "Spade"))

    def test_lead_prefers_ace_liability_suit(self):
        info = PublicInfo(2)
        info.hand_sizes = [3, 10]
        info.voids[1].add("Heart")
        view = info.view_for(0, [1])
        bot = ComputerPlayer("CPU")
        bot.receive_cards([C("10", "Heart"), C("8", "Heart"), C("A", "Club")])
        played = bot.play_turn(None, view)
        self.assertEqual(played, C("A", "Club"))

    def test_lead_prefers_singleton_face_over_low_heart_cluster(self):
        info = PublicInfo(4)
        info.hand_sizes = [5, 8, 8, 8]
        view = info.view_for(0, [1, 2, 3])
        bot = ComputerPlayer("CPU", mc_samples=50)
        bot.receive_cards(
            [
                C("J", "Diamond"),
                C("4", "Heart"),
                C("5", "Heart"),
                C("6", "Heart"),
                C("7", "Club"),
            ]
        )
        played = bot.play_turn(None, view)
        self.assertEqual(played, C("J", "Diamond"))

    def test_follow_dumps_queen_over_two(self):
        info = PublicInfo(3)
        info.hand_sizes = [3, 8, 8]
        info.current_highest = C("6", "Heart")
        info.current_highest_player = 0
        info.led_suit = "Heart"
        view = info.view_for(1, [2])
        bot = ComputerPlayer("CPU", mc_samples=50)
        bot.receive_cards([C("2", "Heart"), C("7", "Heart"), C("Q", "Heart")])
        played = bot.play_turn(cards_of_suit("Heart"), view)
        self.assertEqual(played, C("Q", "Heart"))

    def test_follow_cashes_king_from_length_four_under_eight(self):
        """Lead-shape length must not block follow-cash (game 16e230 T5)."""
        info = PublicInfo(4)
        info.hand_sizes = [9, 9, 9, 9]
        info.current_highest = C("8", "Diamond")
        info.current_highest_player = 1
        info.led_suit = "Diamond"
        view = info.view_for(2, [3, 0])
        bot = ComputerPlayer("CPU", mc_samples=50)
        bot.receive_cards(
            [
                C("2", "Diamond"),
                C("9", "Diamond"),
                C("Q", "Diamond"),
                C("K", "Diamond"),
                C("7", "Club"),
            ]
        )
        played = bot.play_turn(cards_of_suit("Diamond"), view)
        self.assertEqual(played, C("K", "Diamond"))

    def test_follow_cashes_ace_from_length_four_under_two(self):
        """Ace under a 2 must cash even from four clubs (game 16e230 T6)."""
        info = PublicInfo(4)
        info.hand_sizes = [8, 8, 8, 8]
        info.current_highest = C("2", "Club")
        info.current_highest_player = 0
        info.led_suit = "Club"
        view = info.view_for(1, [2, 3])
        bot = ComputerPlayer("CPU", mc_samples=50)
        bot.receive_cards(
            [
                C("3", "Club"),
                C("J", "Club"),
                C("K", "Club"),
                C("A", "Club"),
                C("7", "Diamond"),
            ]
        )
        played = bot.play_turn(cards_of_suit("Club"), view)
        self.assertEqual(played, C("A", "Club"))

    def test_follow_cashes_ace_under_king_despite_length(self):
        info = PublicInfo(3)
        info.hand_sizes = [6, 6, 6]
        info.current_highest = C("K", "Diamond")
        info.current_highest_player = 0
        info.led_suit = "Diamond"
        view = info.view_for(1, [2])
        bot = ComputerPlayer("CPU", mc_samples=50)
        bot.receive_cards(
            [
                C("3", "Diamond"),
                C("4", "Diamond"),
                C("5", "Diamond"),
                C("A", "Diamond"),
                C("2", "Spade"),
            ]
        )
        played = bot.play_turn(cards_of_suit("Diamond"), view)
        self.assertEqual(played, C("A", "Diamond"))

    def test_lead_prefers_queen_over_keeper_two(self):
        info = PublicInfo(3)
        info.hand_sizes = [5, 8, 8]
        view = info.view_for(0, [1, 2])
        bot = ComputerPlayer("CPU", mc_samples=50)
        bot.receive_cards(
            [
                C("7", "Club"),
                C("9", "Diamond"),
                C("Q", "Diamond"),
                C("2", "Heart"),
                C("6", "Spade"),
            ]
        )
        played = bot.play_turn(None, view)
        self.assertEqual(played, C("Q", "Diamond"))

    def test_lead_prefers_singleton_mid_over_keeper_and_long_club(self):
        """bf4a15ae T7/T9: 8D singleton beats 4S / 8C."""
        info = PublicInfo(4)
        info.hand_sizes = [5, 5, 5, 5]
        view = info.view_for(0, [1, 2, 3])
        bot = ComputerPlayer("CPU", mc_samples=40)
        bot.receive_cards(
            [
                C("4", "Club"),
                C("7", "Club"),
                C("8", "Club"),
                C("8", "Diamond"),
                C("4", "Spade"),
            ]
        )
        played = bot.play_turn(None, view)
        self.assertEqual(played, C("8", "Diamond"))

    def test_lead_prefers_mid_spade_over_heart_keeper(self):
        """bf4a15ae T8: 6S over 3H when no faces."""
        info = PublicInfo(3)
        info.hand_sizes = [6, 8, 8]
        view = info.view_for(0, [1, 2])
        bot = ComputerPlayer("CPU", mc_samples=40)
        bot.receive_cards(
            [
                C("3", "Club"),
                C("3", "Diamond"),
                C("3", "Heart"),
                C("2", "Spade"),
                C("3", "Spade"),
                C("6", "Spade"),
            ]
        )
        played = bot.play_turn(None, view)
        self.assertEqual(played, C("6", "Spade"))

    def test_lead_lose_rates_returns_all_candidates(self):
        info = PublicInfo(3)
        info.hand_sizes = [2, 5, 5]
        view = info.view_for(0, [1, 2])
        hand = [C("2", "Club"), C("A", "Club")]
        rates = estimate_lead_lose_rates(view, hand, hand, samples=8)
        self.assertEqual(set(rates), set(hand))
        for p in rates.values():
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)


class TakeDecisionTests(unittest.TestCase):
    def test_refuse_when_two_left(self):
        info = PublicInfo(2)
        info.active_indices = [0, 1]
        info.hand_sizes = [5, 5]
        info.voids[1].add("Heart")
        view = info.view_for(0, [1])
        hand = [C("2", "Heart")]
        self.assertFalse(should_cpu_take(hand, view, 1, i_am_leader=True))

    def test_single_void_large_hand_refuses(self):
        info = PublicInfo(3)
        info.active_indices = [0, 1, 2]
        info.hand_sizes = [5, 5, 5]
        info.voids[1].add("Heart")
        view = info.view_for(0, [1, 2])
        hand = [C("2", "Heart"), C("3", "Club")]
        self.assertFalse(case_a_should_take(view, hand, 1))
        self.assertFalse(should_cpu_take(hand, view, 1, i_am_leader=True))

    def test_case_a_alone_does_not_force_take(self):
        """High unknowns + case-A soft hint → still refuse without MC win."""
        info = PublicInfo(3)
        info.active_indices = [0, 1, 2]
        info.hand_sizes = [8, 3, 8]
        info.voids[1].add("Heart")
        view = info.view_for(0, [1, 2])
        hand = [C("2", "Heart"), C("3", "Club"), C("4", "Club")]
        self.assertTrue(case_a_should_take(view, hand, 1))
        # Many free unknowns (> TAKE_UNKNOWN_MAX) → no take.
        self.assertFalse(should_cpu_take(hand, view, 1, i_am_leader=True))
        self.assertFalse(should_cpu_take(hand, view, 1, i_am_leader=False))

    def test_brick_hand_take_refuses_when_merge_not_better(self):
        """bf4a15ae-style: already large hand, small void neighbor — usually refuse."""
        info = PublicInfo(4)
        info.active_indices = [0, 1, 2, 3]
        info.hand_sizes = [3, 4, 4, 12]
        info.voids[0].add("Club")
        view = info.view_for(3, [0, 1, 2])
        hand = [
            C("2", "Club"),
            C("6", "Club"),
            C("2", "Diamond"),
            C("4", "Diamond"),
            C("6", "Diamond"),
            C("2", "Heart"),
            C("4", "Heart"),
            C("5", "Heart"),
            C("4", "Spade"),
            C("6", "Spade"),
            C("8", "Spade"),
            C("7", "Heart"),
        ]
        # Either unknowns too high or MC does not prefer merge.
        self.assertFalse(should_cpu_take(hand, view, 0, i_am_leader=True))


if __name__ == "__main__":
    unittest.main()
