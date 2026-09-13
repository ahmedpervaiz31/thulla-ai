"""Equivalence-class card raising (play high end of a dead-gap block)."""

import unittest

from thulla.cards import Card, equivalence_class, raise_equivalence
from thulla.info import PublicInfo
from thulla.players import choose_computer_card


def C(number, colour):
    return Card(number, colour)


class EquivalenceClassTests(unittest.TestCase):
    def test_continuous_block(self):
        hand = [C("4", "Heart"), C("5", "Heart"), C("6", "Heart"), C("7", "Heart"), C("8", "Heart")]
        group = equivalence_class(C("4", "Heart"), hand, accounted=set(hand))
        self.assertEqual(group, hand)
        self.assertEqual(
            raise_equivalence(C("4", "Heart"), hand, hand, accounted=set(hand)),
            C("8", "Heart"),
        )

    def test_gap_linked_when_middle_discarded(self):
        hand = [C("3", "Spade"), C("4", "Spade"), C("6", "Spade")]
        accounted = set(hand) | {C("5", "Spade")}
        group = equivalence_class(C("3", "Spade"), hand, accounted=accounted)
        self.assertEqual(group, hand)
        self.assertEqual(
            raise_equivalence(C("3", "Spade"), hand, hand, accounted=accounted),
            C("6", "Spade"),
        )

    def test_ten_jack_ace_with_qk_dead(self):
        hand = [C("10", "Club"), C("J", "Club"), C("A", "Club")]
        accounted = set(hand) | {C("Q", "Club"), C("K", "Club")}
        self.assertEqual(
            raise_equivalence(C("10", "Club"), hand, hand, accounted=accounted),
            C("A", "Club"),
        )

    def test_live_gap_breaks_class(self):
        hand = [C("3", "Spade"), C("4", "Spade"), C("6", "Spade")]
        # 5 still live — two classes
        group = equivalence_class(C("3", "Spade"), hand, accounted=set(hand))
        self.assertEqual(group, [C("3", "Spade"), C("4", "Spade")])
        self.assertEqual(
            raise_equivalence(C("3", "Spade"), hand, hand, accounted=set(hand)),
            C("4", "Spade"),
        )

    def test_risky_lead_raises_low_block(self):
        """High thulla risk used to lead min; must raise to top of continuous block."""
        info = PublicInfo(3)
        info.active_indices = [0, 1, 2]
        info.hand_sizes = [5, 5, 5]
        info.voids[1].add("Heart")  # someone after is void → P=1
        view = info.view_for(0, [1, 2])
        hand = [
            C("4", "Heart"),
            C("5", "Heart"),
            C("6", "Heart"),
            C("7", "Heart"),
            C("8", "Heart"),
            C("2", "Club"),
        ]
        # Only hearts legal for lead from this hand; club also legal on lead.
        moves = list(hand)
        # Force hearts-only by making club also void-risky... actually with Heart void
        # after, policy skips Heart if Club has no void. Give Club a void too so both
        # risky, or only hold hearts.
        hand = [
            C("4", "Heart"),
            C("5", "Heart"),
            C("6", "Heart"),
            C("7", "Heart"),
            C("8", "Heart"),
        ]
        moves = list(hand)
        card = choose_computer_card(hand, moves, None, view, samples=20)
        self.assertEqual(card, C("8", "Heart"))


if __name__ == "__main__":
    unittest.main()
