import random

from .cards import Card, NUMBER_CARDS, parse_card, valid_moves


class BasePlayer:
    def __init__(self, name):
        self.name = name
        self.hand = []

    def receive_cards(self, cards):
        self.hand.extend(cards)
        self.sort_hand()

    def sort_hand(self):
        self.hand.sort(key=lambda card: (card.colour, NUMBER_CARDS.index(card.number)))

    def print_hand(self):
        print(f"{self.name} has {len(self.hand)} cards:")
        for card in self.hand:
            print(f"- {card}")
        print("\n")

    def play_turn(self, expected_cards):
        raise NotImplementedError

    def offer_take(self, target_name, n_cards):
        return False


class HumanPlayer(BasePlayer):
    def offer_take(self, target_name, n_cards):
        while True:
            ans = input(f"Take {target_name}'s {n_cards} cards? [y/n]: ").strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no", ""):
                return False
            print("Please answer y or n.")

    def play_turn(self, expected_cards):
        moves = valid_moves(self.hand, expected_cards)
        must_follow = bool(expected_cards) and any(card in expected_cards for card in self.hand)

        print(f"Your cards ({self.name}):")
        self.print_hand()

        card = self._read_card()
        while card not in moves:
            print("Invalid move.")
            if must_follow:
                print("You must play one of these:")
                for c in moves:
                    print(f"- {c}")
            elif card not in self.hand:
                print("You don't even have that card.")
            else:
                print("You don't have that card or it's not a valid move.")
            card = self._read_card()

        print(f"{self.name} played: {card}")
        self.hand.remove(card)
        return card

    def _read_card(self):
        line = input(f"[{self.name}] Card (e.g. AH, 10S, Q hearts): ")
        card = parse_card(line)
        if card is not None:
            return card

        number = input(f"[{self.name}] Number: ").upper().strip()
        colour = input(f"[{self.name}] Card(Colour): ").strip().capitalize()
        if colour.endswith("s"):
            colour = colour[:-1]
        parsed = parse_card(f"{number} {colour}")
        return parsed if parsed is not None else Card(number, colour)


class ComputerPlayer(BasePlayer):
    def play_turn(self, expected_cards):
        moves = valid_moves(self.hand, expected_cards)
        card = random.choice(moves)
        print(f"{self.name} played: {card}")
        self.hand.remove(card)
        return card

    def offer_take(self, target_name, n_cards):
        return False


class ScriptedPlayer(BasePlayer):
    """Deterministic player for tests: queued cards and optional take answers."""

    def __init__(self, name, take_decisions=None):
        super().__init__(name)
        self.play_queue = []
        self.take_decisions = list(take_decisions or [])

    def queue_plays(self, cards):
        self.play_queue.extend(cards)

    def offer_take(self, target_name, n_cards):
        if not self.take_decisions:
            return False
        return bool(self.take_decisions.pop(0))

    def play_turn(self, expected_cards):
        if not self.play_queue:
            raise RuntimeError(f"{self.name} has no scripted card to play")
        card = self.play_queue.pop(0)
        moves = valid_moves(self.hand, expected_cards)
        if card not in moves:
            raise ValueError(f"{self.name} scripted illegal card {card}; legal: {moves}")
        self.hand.remove(card)
        return card
