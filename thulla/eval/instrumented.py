"""Instrumented CPU that logs P(thulla) vs oracle voids without leaking into play."""

from thulla.cards import valid_moves
from thulla.players import ComputerPlayer, choose_computer_card


EVAL_MC_SAMPLES = 50


class InstrumentedComputerPlayer(ComputerPlayer):
    def __init__(self, name, seat, records, mc_samples=EVAL_MC_SAMPLES):
        super().__init__(name, mc_samples=mc_samples, allow_late_take=False)
        self.seat = seat
        self.records = records
        self.table_players = None  # set to full player list after construction

    def play_turn(self, expected_cards, view=None):
        moves = valid_moves(self.hand, expected_cards)
        if view is not None:
            must_follow = bool(expected_cards) and any(
                card in expected_cards for card in self.hand
            )
            if must_follow:
                suit = expected_cards[0].colour
                seats = view.players_after_me_this_trick()
                p_hat = view.estimate_thulla_prob(
                    suit, self.hand, seats_after=seats, samples=self.mc_samples
                )
                y = self._oracle_void(seats, suit)
                self.records.append((p_hat, y))
                card = choose_computer_card(
                    self.hand, moves, expected_cards, view, samples=self.mc_samples
                )
                self.hand.remove(card)
                return card

            card = choose_computer_card(
                self.hand, moves, expected_cards, view, samples=self.mc_samples
            )
            seats = view.players_after_me_this_trick()
            if not seats:
                seats = [p for p in view.active_indices if p != view.me]
            p_hat = view.estimate_thulla_prob(
                card.colour, self.hand, seats_after=seats, samples=self.mc_samples
            )
            y = self._oracle_void(seats, card.colour)
            self.records.append((p_hat, y))
            self.hand.remove(card)
            return card

        card = choose_computer_card(
            self.hand, moves, expected_cards, view, samples=self.mc_samples
        )
        self.hand.remove(card)
        return card

    def _oracle_void(self, seats, suit):
        if not self.table_players:
            return 0
        for idx in seats:
            hand = self.table_players[idx].hand
            if not any(c.colour == suit for c in hand):
                return 1
        return 0
