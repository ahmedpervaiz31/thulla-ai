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

    def test_follow_soft_when_safe_with_cards_left(self):
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
        self.assertEqual(played, C("8", "Spade"))

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

    def test_case_a_leader_takes_void_neighbor(self):
        info = PublicInfo(3)
        info.active_indices = [0, 1, 2]
        info.hand_sizes = [5, 5, 5]
        info.voids[1].add("Heart")
        view = info.view_for(0, [1, 2])
        hand = [C("2", "Heart"), C("3", "Club")]
        self.assertTrue(case_a_should_take(view, hand, 1))
        self.assertTrue(should_cpu_take(hand, view, 1, i_am_leader=True))
        self.assertFalse(should_cpu_take(hand, view, 1, i_am_leader=False))


if __name__ == "__main__":
    unittest.main()
