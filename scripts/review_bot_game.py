"""One verbose game: smart bot vs 3 randoms for manual review."""

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thulla.cards import format_hand, valid_moves
from thulla.game import ThullaGame
from thulla.players import ComputerPlayer, RandomPlayer, choose_computer_card


class ReviewBot(ComputerPlayer):
    """Same as ComputerPlayer, but prints hand + move each turn."""

    def play_turn(self, expected_cards, view=None):
        moves = valid_moves(self.hand, expected_cards)
        print(f"\n>>> {self.name} HAND ({len(self.hand)})")
        print(format_hand(self.hand))
        if expected_cards is None:
            print(">>> decision: LEAD")
        elif any(c in expected_cards for c in self.hand):
            print(f">>> decision: FOLLOW {expected_cards[0].colour}")
            if view is not None:
                seats = view.players_after_me_this_trick()
                p = view.estimate_thulla_prob(
                    expected_cards[0].colour,
                    self.hand,
                    seats_after=seats,
                    samples=self.mc_samples,
                )
                print(f">>> P(thulla)={p:.2f}  highest={view.current_highest}")
        else:
            print(f">>> decision: THULLA (void in {expected_cards[0].colour})")
            if view is not None:
                print(f">>> victim would be seat {view.current_highest_player} "
                      f"with {view.current_highest}")

        card = choose_computer_card(
            self.hand, moves, expected_cards, view, samples=self.mc_samples
        )
        print(f">>> {self.name} plays {card}")
        self.hand.remove(card)
        return card

    def offer_take(self, target_name, n_cards, view=None, neighbor_idx=None, i_am_leader=False):
        decision = super().offer_take(
            target_name, n_cards, view, neighbor_idx, i_am_leader
        )
        print(
            f">>> {self.name} take offer: {target_name} ({n_cards} cards) "
            f"leader={i_am_leader} -> {'YES' if decision else 'no'}"
        )
        return decision


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    random.seed(seed)
    print(f"SEED={seed}")
    print("BOT = ReviewBot (ComputerPlayer) vs Rand1/2/3\n")

    bot = ReviewBot("BOT", mc_samples=200, allow_late_take=True)
    players = [
        bot,
        RandomPlayer("Rand1"),
        RandomPlayer("Rand2"),
        RandomPlayer("Rand3"),
    ]
    game = ThullaGame(players, verbose=True)
    random.seed(seed)
    game.shuffle_and_deal()

    print("\n=== Starting hands ===")
    for p in players:
        print(f"{p.name} ({len(p.hand)})")
        print(format_hand(p.hand))
        print()

    game.game_loop()
    game.print_winners()
    print(f"\n(re-run with: python scripts/review_bot_game.py {seed})")


if __name__ == "__main__":
    main()
