import random

from .cards import Card, create_deck, cards_of_suit


class ThullaGame:
    def __init__(self, players, verbose=True):
        self.players = players
        self.player_cnt = len(players)
        self.all_cards = create_deck()
        self.total_cards = len(self.all_cards)
        self.verbose = verbose

        self.ace_spades_holder_idx = 0
        self.winners = []
        self.active_player_indices = list(range(self.player_cnt))

    def log(self, *args, **kwargs):
        if self.verbose:
            print(*args, **kwargs)

    def shuffle_and_deal(self):
        random.shuffle(self.all_cards)
        for p in self.players:
            p.hand = []

        temp_hands = [[] for _ in range(self.player_cnt)]
        ace_spades = Card(number="A", colour="Spade")

        for i, card in enumerate(self.all_cards):
            turn = i % self.player_cnt
            if card == ace_spades:
                self.ace_spades_holder_idx = turn
                self.log(f"Ace of Spades holder is Player {turn} ({self.players[turn].name})")
            temp_hands[turn].append(card)

        for i, p in enumerate(self.players):
            p.receive_cards(temp_hands[i])

        self.active_player_indices = list(range(self.player_cnt))
        self.winners = []

    def set_hands(self, hands, ace_spades_holder_idx=None):
        """Assign hands for tests / scripted deals. Does not shuffle."""
        if len(hands) != self.player_cnt:
            raise ValueError("hands must match player count")
        for p, h in zip(self.players, hands):
            p.hand = []
            p.receive_cards(list(h))
        self.active_player_indices = [i for i, p in enumerate(self.players) if p.hand]
        self.winners = []
        if ace_spades_holder_idx is not None:
            self.ace_spades_holder_idx = ace_spades_holder_idx

    def get_expected_cards(self, current_colour):
        if current_colour is None:
            return None
        return cards_of_suit(current_colour)

    def next_active(self, from_idx):
        """Next still-in player clockwise after from_idx, or None."""
        for i in range(1, self.player_cnt + 1):
            idx = (from_idx + i) % self.player_cnt
            if idx in self.active_player_indices:
                return idx
        return None

    def ensure_leader_active(self, leader_idx):
        if leader_idx in self.active_player_indices:
            return leader_idx
        return self.next_active(leader_idx)

    def active_in_order(self, start_idx):
        start = start_idx if start_idx in self.active_player_indices else self.next_active(start_idx)
        if start is None:
            return []
        order = [start]
        idx = self.next_active(start)
        while idx is not None and idx != start:
            order.append(idx)
            idx = self.next_active(idx)
        return order

    def take_phase(self, leader_idx):
        """One clockwise pass from the leader. Each still-in player may take the next still-in clockwise."""
        leader_idx = self.ensure_leader_active(leader_idx)
        if leader_idx is None or len(self.active_player_indices) <= 1:
            return leader_idx

        to_ask = self.active_in_order(leader_idx)
        for idx in to_ask:
            if idx not in self.active_player_indices:
                continue
            if len(self.active_player_indices) <= 1:
                break
            target = self.next_active(idx)
            if target is None or target == idx:
                break
            taker = self.players[idx]
            taken = self.players[target]
            n_cards = len(taken.hand)
            if not taker.offer_take(taken.name, n_cards):
                continue
            cards = list(taken.hand)
            taken.hand.clear()
            taker.receive_cards(cards)
            self.log(f"{taker.name} takes {n_cards} cards from {taken.name}.")
            self._record_got_away(target)

        return self.ensure_leader_active(leader_idx)

    def resolve_trick(self, leader_idx, first_trick=False):
        """Play one trick. Returns the player who should lead next (before empty-hand check)."""
        leader_idx = self.ensure_leader_active(leader_idx)
        if leader_idx is None:
            return None

        players_in_turn_order = self.active_in_order(leader_idx)
        stack = []
        colour = "Spade" if first_trick else None
        highest_card = None
        highest_idx = leader_idx

        self.log(f"Leader: {self.players[leader_idx].name}")

        for i, turn_idx in enumerate(players_in_turn_order):
            player = self.players[turn_idx]
            self.log(f"Stack: {stack}")

            if first_trick:
                expected = [Card("A", "Spade")] if i == 0 else self.get_expected_cards("Spade")
            elif i == 0:
                expected = None
            else:
                expected = self.get_expected_cards(colour)

            card = player.play_turn(expected)
            stack.append(card)

            if i == 0:
                colour = card.colour
                highest_card = card
                highest_idx = turn_idx
                continue

            if card.colour != colour:
                if first_trick:
                    continue
                victim = self.players[highest_idx]
                self.log(
                    f"THULLA! {player.name} played {card.colour}, expected {colour}s"
                )
                self.log(f"Victim is {victim.name} (Highest card holder)")
                self.log(f"{victim.name} picks up {len(stack)} cards.")
                victim.receive_cards(stack)
                return highest_idx

            if card > highest_card:
                highest_card = card
                highest_idx = turn_idx
                self.log(f"New highest: {highest_card} by {player.name}")

        self.log(f"Trick discarded. Highest {colour} was {highest_card} by {self.players[highest_idx].name}")
        return highest_idx

    def check_got_away(self, from_idx):
        """Empty hands get away in clockwise play order from from_idx. Lead may pass."""
        emptied = [idx for idx in self.active_in_order(from_idx) if len(self.players[idx].hand) == 0]
        for idx in emptied:
            self._record_got_away(idx)
        return self.ensure_leader_active(from_idx)

    def _record_got_away(self, idx):
        if idx not in self.active_player_indices:
            return
        player = self.players[idx]
        self.winners.append(player)
        self.active_player_indices.remove(idx)
        self.log(f"{player.name} has finished!")

    def remaining_players(self):
        return [self.players[i] for i in self.active_player_indices]

    def game_loop(self):
        self.log("\n--- Starting Game ---")
        self.log("\n--- First Round (Ace of Spades) ---")
        leader = self.ace_spades_holder_idx
        self.resolve_trick(leader, first_trick=True)
        self.check_got_away(self.ace_spades_holder_idx)
        leader = self.ensure_leader_active(self.ace_spades_holder_idx)

        while len(self.active_player_indices) > 1:
            self.log("\n----------------- Next Turn -----------------")
            leader = self.take_phase(leader)
            if leader is None or len(self.active_player_indices) <= 1:
                break
            leader = self.resolve_trick(leader, first_trick=False)
            leader = self.check_got_away(leader)

    def print_winners(self):
        print("\nGame Over!")
        print("Finish order:")
        for i, p in enumerate(self.winners):
            print(f"{i + 1}. {p.name}")
        leftover = self.remaining_players()
        if leftover:
            print(f"Loser: {leftover[0].name}")
