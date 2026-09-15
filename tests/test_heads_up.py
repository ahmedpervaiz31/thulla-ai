import time
import unittest
from unittest import mock

from thulla.advise import _exact_advice
from thulla.cards import Card, create_deck
from thulla.heads_up import (
    DEFAULT_MAX_MS,
    exact_best_move,
    exact_best_move_with_value,
    exact_move_outcome,
    exact_move_value,
    try_exact_with_value_from_view,
)
from thulla.info import PublicInfo
from thulla.players import ComputerPlayer, choose_computer_card


def C(number, colour):
    return Card(number, colour)


class ExactHeadsUpTests(unittest.TestCase):
    def test_forced_win_singleton_ace_spade(self):
        """Lead AS; opp follows and keeps a side card — I empty first."""
        me = [C("A", "Spade")]
        opp = [C("2", "Spade"), C("3", "Diamond")]
        card = exact_best_move(me, opp, i_am_leader=True)
        self.assertEqual(card, C("A", "Spade"))
        self.assertEqual(exact_move_outcome(me, opp, card, i_am_leader=True), 1)

    def test_thulla_on_opp_last_card_loses(self):
        """Void lead when opp's only card is off-suit: they empty on thulla, I pick up and lose."""
        me = [C("2", "Club")]
        opp = [C("3", "Diamond")]
        card = exact_best_move(me, opp, i_am_leader=True)
        self.assertEqual(card, C("2", "Club"))
        self.assertEqual(exact_move_outcome(me, opp, card, i_am_leader=True), -1)

    def test_strip_spades_forces_win(self):
        me = [C("A", "Spade"), C("K", "Spade")]
        opp = [C("2", "Spade"), C("3", "Spade")]
        card = exact_best_move(me, opp, i_am_leader=True)
        self.assertEqual(card.colour, "Spade")
        self.assertEqual(exact_move_outcome(me, opp, card, i_am_leader=True), 1)

    def test_club_lead_loses_when_spade_strip_wins(self):
        me = [C("A", "Spade"), C("K", "Spade")]
        opp = [C("2", "Spade"), C("3", "Spade")]
        self.assertEqual(
            exact_move_outcome(me, opp, C("A", "Spade"), i_am_leader=True), 1
        )

    def test_all_club_opponent_leads_acquired_club(self):
        me = [C("8", "Diamond"), C("2", "Club")]
        opp = [C("4", "Club"), C("5", "Club")]
        card = exact_best_move(me, opp, i_am_leader=True)
        self.assertEqual(card, C("2", "Club"))
        self.assertGreater(
            exact_move_outcome(me, opp, C("2", "Club"), i_am_leader=True),
            exact_move_outcome(me, opp, C("8", "Diamond"), i_am_leader=True),
        )

    def test_all_club_first_lead_must_thulla(self):
        me = [C("8", "Diamond"), C("J", "Spade")]
        opp = [C("2", "Club"), C("4", "Club"), C("5", "Club")]
        card = exact_best_move(me, opp, i_am_leader=True)
        self.assertIn(card, me)
        self.assertIn(exact_move_outcome(me, opp, card, i_am_leader=True), (-1, 1))

    def test_respond_when_opp_already_empty_loses(self):
        me = [C("2", "Heart"), C("K", "Heart")]
        opp_left = []
        card = exact_best_move(
            me,
            opp_left,
            i_am_leader=False,
            lead_card=C("3", "Heart"),
            highest=C("3", "Heart"),
        )
        self.assertIn(card, me)
        self.assertEqual(
            exact_move_outcome(
                me,
                opp_left,
                card,
                i_am_leader=False,
                lead_card=C("3", "Heart"),
                highest=C("3", "Heart"),
            ),
            -1,
        )

    def test_lose_gracefully_prefers_4c_over_8h(self):
        """6880f30e T19: both lines may lose; prefer clean club over heart self-thulla."""
        me = [C("4", "Club"), C("8", "Heart")]
        opp = [C("3", "Club"), C("4", "Spade"), C("2", "Diamond")]
        card = exact_best_move(me, opp, i_am_leader=True)
        self.assertEqual(card, C("4", "Club"))
        v4 = exact_move_value(me, opp, C("4", "Club"), i_am_leader=True)
        v8 = exact_move_value(me, opp, C("8", "Heart"), i_am_leader=True)
        self.assertIsNotNone(v4)
        self.assertIsNotNone(v8)
        self.assertGreaterEqual(v4, v8)
        self.assertNotEqual(card, C("8", "Heart"))

    def test_best_move_with_value_matches_outcome(self):
        me = [C("A", "Spade"), C("K", "Spade")]
        opp = [C("2", "Spade"), C("3", "Spade")]
        card, value = exact_best_move_with_value(me, opp, i_am_leader=True)
        self.assertEqual(card.colour, "Spade")
        self.assertEqual(value[0], 1)
        self.assertEqual(exact_move_outcome(me, opp, card, i_am_leader=True), 1)

    def test_principal_line_forced_spade_strip(self):
        from thulla.heads_up import exact_principal_line

        me = [C("A", "Spade"), C("K", "Spade")]
        opp = [C("2", "Spade"), C("3", "Spade")]
        card = exact_best_move(me, opp, i_am_leader=True)
        line = exact_principal_line(
            me, opp, i_am_leader=True, first_card=card, max_ms=None
        )
        self.assertTrue(line)
        self.assertEqual(line[0]["side"], "you")
        self.assertEqual(line[0]["card"], card.code())
        codes = [s["card"] for s in line if s.get("card")]
        self.assertTrue(any(c.endswith("S") for c in codes))
        self.assertTrue(
            any("win" in (s.get("note") or "").lower() for s in line),
            msg=line,
        )

    def test_respond_root_values_not_poisoned_by_sibling_alpha(self):
        """Regression: shared root alpha once marked 2C as a false forced win."""
        me = [C("2", "Club"), C("8", "Club"), C("9", "Club")]
        opp = [
            C("3", "Club"),
            C("4", "Diamond"),
            C("2", "Heart"),
            C("4", "Heart"),
            C("6", "Heart"),
            C("7", "Heart"),
            C("9", "Heart"),
            C("5", "Spade"),
        ]
        lead = C("4", "Club")
        card, value = exact_best_move_with_value(
            me,
            opp,
            i_am_leader=False,
            lead_card=lead,
            highest=lead,
            max_ms=None,
        )
        self.assertEqual(card, C("9", "Club"))
        self.assertEqual(value[0], 1)
        self.assertEqual(
            exact_move_outcome(
                me, opp, C("2", "Club"), i_am_leader=False, lead_card=lead, highest=lead
            ),
            -1,
        )

    def test_hard_2v12_respects_time_cap(self):
        """Seed-17-style 2+12 must not hang for tens of seconds."""
        import random

        deck = create_deck()
        random.seed(17)
        random.shuffle(deck)
        me = list(deck[:2])
        opp = list(deck[2:14])
        self.assertEqual(len(me) + len(opp), 14)
        t0 = time.perf_counter()
        card = exact_best_move(me, opp, i_am_leader=True, max_ms=DEFAULT_MAX_MS)
        dt = time.perf_counter() - t0
        # Allow scheduler slack well under the old ~55s miss.
        self.assertLess(dt, 2.0)
        if card is not None:
            self.assertIn(card, me)


class HeadsUpIntegrationTests(unittest.TestCase):
    def test_computer_uses_exact_in_heads_up(self):
        info = PublicInfo(2)
        info.active_indices = [0, 1]
        me = [C("A", "Spade"), C("K", "Spade")]
        opp = [C("2", "Spade"), C("3", "Spade")]
        keep = set(me) | set(opp)
        info.discarded = {c for c in create_deck() if c not in keep}
        info.hand_sizes = [2, 2]
        view = info.view_for(0, [1])
        self.assertIsNotNone(view.deduced_hand(1, me))
        bot = ComputerPlayer("CPU")
        bot.receive_cards(list(me))
        played = bot.play_turn(None, view)
        self.assertEqual(played.colour, "Spade")

    def test_choose_computer_card_exact_path(self):
        info = PublicInfo(2)
        info.active_indices = [0, 1]
        me = [C("A", "Spade")]
        opp = [C("2", "Spade"), C("3", "Diamond")]
        keep = set(me) | set(opp)
        info.discarded = {c for c in create_deck() if c not in keep}
        info.hand_sizes = [1, 2]
        view = info.view_for(0, [1])
        card = choose_computer_card(me, list(me), None, view, samples=10)
        self.assertEqual(card, C("A", "Spade"))

    def test_advise_reuses_exact_value_without_second_search(self):
        info = PublicInfo(2)
        info.active_indices = [0, 1]
        me = [C("A", "Spade"), C("K", "Spade")]
        opp = [C("2", "Spade"), C("3", "Spade")]
        keep = set(me) | set(opp)
        info.discarded = {c for c in create_deck() if c not in keep}
        info.hand_sizes = [2, 2]
        view = info.view_for(0, [1])
        card, value = try_exact_with_value_from_view(
            me, list(me), None, view, max_ms=None
        )
        self.assertIsNotNone(card)
        self.assertEqual(value[0], 1)
        with mock.patch("thulla.heads_up.exact_move_outcome") as boom:
            out_card, steps, extra = _exact_advice(card, "lead", value[0])
        self.assertEqual(out_card, card)
        self.assertEqual(extra["outcome"], 1)
        self.assertTrue(extra["exact_1v1"])
        self.assertTrue(any(s["label"] == "EXACT 1v1" for s in steps))
        boom.assert_not_called()


if __name__ == "__main__":
    unittest.main()
