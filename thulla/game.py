import random
from dataclasses import dataclass, field

from .cards import Card, create_deck, cards_of_suit, format_cards, valid_moves
from .info import PublicInfo


@dataclass
class TrickState:
    leader_idx: int
    first_trick: bool
    order: list
    colour: str | None = None
    stack: list = field(default_factory=list)
    highest_card: Card | None = None
    highest_idx: int | None = None
    plays: list = field(default_factory=list)
    seat_pos: int = 0
    done: bool = False
    result: str | None = None  # "thulla" | "trick_won"
    next_leader: int | None = None


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
        self.trick_number = 0
        self.info = PublicInfo(self.player_cnt)

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
                self.log(f"{self.players[turn].name} has AS")
            temp_hands[turn].append(card)

        for i, p in enumerate(self.players):
            p.receive_cards(temp_hands[i])

        self.active_player_indices = list(range(self.player_cnt))
        self.winners = []
        self.info.reset(self.active_player_indices)
        self.info.sync_hands(self.players)

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
        self.info.reset(self.active_player_indices)
        self.info.sync_hands(self.players)

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

    def begin_trick(self, leader_idx, first_trick=False):
        """Start a trick. Returns TrickState or None if no active leader."""
        leader_idx = self.ensure_leader_active(leader_idx)
        if leader_idx is None:
            return None

        order = self.active_in_order(leader_idx)
        colour = "Spade" if first_trick else None

        self.trick_number += 1
        if first_trick:
            self.log(f"\n--- Trick {self.trick_number}  AS lead (no thulla) ---")
        else:
            self.log(f"\n--- Trick {self.trick_number} ---")
        self.log(self._status_line())
        self.log(f"Lead: {self.players[leader_idx].name}")
        self.info.sync_hands(self.players)

        return TrickState(
            leader_idx=leader_idx,
            first_trick=first_trick,
            order=order,
            colour=colour,
            highest_idx=leader_idx,
        )

    def expected_for_seat(self, trick: TrickState, seat_idx: int):
        """Legal-expectation set for the seat about to play (same rules as resolve_trick)."""
        try:
            i = trick.order.index(seat_idx)
        except ValueError:
            return None
        if i != trick.seat_pos:
            return None
        if trick.first_trick:
            return [Card("A", "Spade")] if i == 0 else self.get_expected_cards("Spade")
        if i == 0:
            return None
        return self.get_expected_cards(trick.colour)

    def view_for_seat(self, trick: TrickState, seat_idx: int):
        i = trick.order.index(seat_idx)
        remaining_after = trick.order[i + 1 :]
        self.info.sync_hands(self.players)
        return self.info.view_for(seat_idx, remaining_after)

    def apply_play(self, trick: TrickState, seat_idx: int, card: Card):
        """
        Apply one already-chosen card. Card must still be in the player's hand.
        Returns 'continue' | 'thulla' | 'trick_won'.
        """
        if trick.done:
            raise RuntimeError("trick already finished")
        if trick.seat_pos >= len(trick.order) or trick.order[trick.seat_pos] != seat_idx:
            raise ValueError(f"not seat {seat_idx}'s turn")

        player = self.players[seat_idx]
        expected = self.expected_for_seat(trick, seat_idx)
        # play_turn() may have already removed the card (CLI path).
        if card in player.hand:
            moves = valid_moves(player.hand, expected)
            if card not in moves:
                raise ValueError(f"illegal card {card}; legal: {moves}")
            player.hand.remove(card)
        else:
            hand_before = list(player.hand) + [card]
            moves = valid_moves(hand_before, expected)
            if card not in moves:
                raise ValueError(f"illegal card {card}; legal: {moves}")

        i = trick.seat_pos
        colour_before = trick.colour

        trick.stack.append(card)
        trick.plays.append((player.name, card))
        self.log(f"  {player.name:6} {card}")
        self.info.note_play(seat_idx, card, colour_before)

        if i == 0:
            trick.colour = card.colour
            trick.highest_card = card
            trick.highest_idx = seat_idx
            trick.seat_pos += 1
            if trick.seat_pos >= len(trick.order):
                return self._finish_clean_trick(trick)
            return "continue"

        if card.colour != trick.colour:
            if trick.first_trick:
                trick.seat_pos += 1
                if trick.seat_pos >= len(trick.order):
                    return self._finish_clean_trick(trick)
                return "continue"
            victim = self.players[trick.highest_idx]
            table = "  ".join(f"{name} {played}" for name, played in trick.plays)
            self.log(f"  THULLA by {player.name}")
            self.log(f"  {victim.name} picks up {len(trick.stack)}: {format_cards(trick.stack)}")
            self.log(f"  {table}")
            victim.receive_cards(trick.stack)
            self.info.finish_thulla(trick.highest_idx, trick.stack)
            trick.done = True
            trick.result = "thulla"
            trick.next_leader = trick.highest_idx
            return "thulla"

        if card > trick.highest_card:
            trick.highest_card = card
            trick.highest_idx = seat_idx

        trick.seat_pos += 1
        if trick.seat_pos >= len(trick.order):
            return self._finish_clean_trick(trick)
        return "continue"

    def _finish_clean_trick(self, trick: TrickState):
        winner = self.players[trick.highest_idx]
        self.log(f"  Discarded | highest {trick.highest_card} ({winner.name} leads)")
        self.info.finish_clean(trick.stack)
        trick.done = True
        trick.result = "trick_won"
        trick.next_leader = trick.highest_idx
        return "trick_won"

    def take_offer_context(self, leader_idx, taker_idx):
        """Return (target_idx, n_cards, view) for a take offer, or None if not applicable.

        Heads-up (≤2 active): takes are disabled — asking is effectively giving up.
        """
        leader_idx = self.ensure_leader_active(leader_idx)
        if leader_idx is None or len(self.active_player_indices) <= 2:
            return None
        if taker_idx not in self.active_player_indices:
            return None
        target = self.next_active(taker_idx)
        if target is None or target == taker_idx:
            return None
        taken = self.players[target]
        n_cards = len(taken.hand)
        remaining_after = [p for p in self.active_in_order(taker_idx) if p != taker_idx]
        self.info.sync_hands(self.players)
        view = self.info.view_for(taker_idx, remaining_after)
        return target, n_cards, view

    def apply_take(self, leader_idx, taker_idx, accept: bool):
        """
        Apply a completed take (asker already said yes and victim consented, or accept=False skips).
        Returns new leader index (ensure_leader_active) after this decision.
        """
        ctx = self.take_offer_context(leader_idx, taker_idx)
        if ctx is None:
            return self.ensure_leader_active(leader_idx)
        target, n_cards, _view = ctx
        if not accept:
            return self.ensure_leader_active(leader_idx)

        taker = self.players[taker_idx]
        taken = self.players[target]
        cards = list(taken.hand)
        taken.hand.clear()
        taker.receive_cards(cards)
        self.info.note_take(taker_idx, target, cards)
        self.info.sync_hands(self.players)
        self.log(f"{taker.name} takes {taken.name}'s {n_cards} cards ({format_cards(cards)})")
        self._record_got_away(target)
        return self.ensure_leader_active(leader_idx)

    def take_phase(self, leader_idx):
        """One clockwise pass: each player may ask next clockwise; victim may refuse."""
        leader_idx = self.ensure_leader_active(leader_idx)
        # Disabled in heads-up (≤2): taking the opponent is just resigning.
        if leader_idx is None or len(self.active_player_indices) <= 2:
            return leader_idx

        self.info.sync_hands(self.players)
        to_ask = self.active_in_order(leader_idx)
        for idx in to_ask:
            if idx not in self.active_player_indices:
                continue
            if len(self.active_player_indices) <= 2:
                break
            target = self.next_active(idx)
            if target is None or target == idx:
                break
            taker = self.players[idx]
            taken = self.players[target]
            n_cards = len(taken.hand)
            remaining_after = [p for p in self.active_in_order(idx) if p != idx]
            view = self.info.view_for(idx, remaining_after)
            wants = taker.offer_take(
                taken.name,
                n_cards,
                view=view,
                neighbor_idx=target,
                i_am_leader=(idx == leader_idx),
            )
            if not wants:
                continue
            victim_view = self.info.view_for(target, [p for p in self.active_in_order(target) if p != target])
            gives = taken.offer_give(
                taker.name,
                n_cards,
                view=victim_view,
                asker_idx=idx,
            )
            if not gives:
                self.log(f"{taken.name} refuses to give cards to {taker.name}")
                continue
            self.apply_take(leader_idx, idx, True)

        return self.ensure_leader_active(leader_idx)

    def resolve_trick(self, leader_idx, first_trick=False):
        """Play one trick. Returns the player who should lead next (before empty-hand check)."""
        trick = self.begin_trick(leader_idx, first_trick=first_trick)
        if trick is None:
            return None

        while not trick.done:
            turn_idx = trick.order[trick.seat_pos]
            player = self.players[turn_idx]
            expected = self.expected_for_seat(trick, turn_idx)
            view = self.view_for_seat(trick, turn_idx)
            card = player.play_turn(expected, view)
            self.apply_play(trick, turn_idx, card)

        return trick.next_leader

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
        self.info.note_got_away(idx)
        self.log(f"{player.name} got away")

    def remaining_players(self):
        return [self.players[i] for i in self.active_player_indices]

    def _status_line(self):
        parts = []
        for i in range(self.player_cnt):
            if i in self.active_player_indices:
                parts.append(f"{self.players[i].name} {len(self.players[i].hand)}")
        return "In: " + " | ".join(parts)

    def game_loop(self):
        self.trick_number = 0
        self.log("Thulla")
        leader = self.ace_spades_holder_idx
        self.resolve_trick(leader, first_trick=True)
        self.check_got_away(self.ace_spades_holder_idx)
        leader = self.ensure_leader_active(self.ace_spades_holder_idx)

        while len(self.active_player_indices) > 1:
            lead_name = self.players[leader].name if leader is not None else "?"
            self.log(f"\nBefore trick {self.trick_number + 1} | lead {lead_name} | take?")
            leader = self.take_phase(leader)
            if leader is None or len(self.active_player_indices) <= 1:
                break
            leader = self.resolve_trick(leader, first_trick=False)
            leader = self.check_got_away(leader)

    def print_winners(self):
        print("\nGame over")
        for i, p in enumerate(self.winners):
            print(f"  {i + 1}. {p.name}")
        leftover = self.remaining_players()
        if leftover:
            print(f"  Loser: {leftover[0].name}")
