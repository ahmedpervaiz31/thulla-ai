import random

from .cards import Card, NUMBER_CARDS, parse_card, valid_moves, format_hand, format_cards
from .prob import (
    _liability_score,
    case_a_should_take,
    compare_take_lose_rates,
    count_free_unknown,
    estimate_lead_lose_rates,
)


class BasePlayer:
    def __init__(self, name):
        self.name = name
        self.hand = []

    def receive_cards(self, cards):
        self.hand.extend(cards)
        self.sort_hand()

    def sort_hand(self):
        self.hand.sort(key=lambda card: (card.colour, NUMBER_CARDS.index(card.number)))

    def play_turn(self, expected_cards, view=None):
        raise NotImplementedError

    def offer_take(self, target_name, n_cards, view=None, neighbor_idx=None, i_am_leader=False):
        return False

    def offer_give(self, asker_name, n_cards, view=None, asker_idx=None):
        """Victim consents to hand over cards. Default: yes."""
        return True


class HumanPlayer(BasePlayer):
    def offer_take(self, target_name, n_cards, view=None, neighbor_idx=None, i_am_leader=False):
        while True:
            ans = input(
                f"[{self.name}] Ask for {target_name}'s {n_cards} cards? [y/n] "
            ).strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no", ""):
                return False
            print("  y or n")

    def offer_give(self, asker_name, n_cards, view=None, asker_idx=None):
        while True:
            ans = input(
                f"[{self.name}] {asker_name} asks for your {n_cards} cards. Give them? [y/n] "
            ).strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no", ""):
                return False
            print("  y or n")

    def play_turn(self, expected_cards, view=None):
        moves = valid_moves(self.hand, expected_cards)
        must_follow = bool(expected_cards) and any(card in expected_cards for card in self.hand)

        print(f"\n[{self.name}] {len(self.hand)} cards")
        print(format_hand(self.hand))
        if expected_cards is None:
            print("  Lead any card")
        elif must_follow:
            suit = expected_cards[0].colour
            print(f"  Follow {suit}: {format_cards(moves)}")
        else:
            suit = expected_cards[0].colour
            print(f"  Void in {suit} - any card (thulla)")

        card = self._read_card()
        while card not in moves:
            if must_follow:
                print(f"  Illegal - follow with {format_cards(moves)}")
            elif card not in self.hand:
                print("  That card is not in your hand")
            else:
                print("  Illegal card")
            card = self._read_card()

        self.hand.remove(card)
        return card

    def _read_card(self):
        line = input(f"[{self.name}] Card: ")
        card = parse_card(line)
        if card is not None:
            return card

        number = input(f"[{self.name}] Number: ").upper().strip()
        colour = input(f"[{self.name}] Card(Colour): ").strip().capitalize()
        if colour.endswith("s"):
            colour = colour[:-1]
        parsed = parse_card(f"{number} {colour}")
        return parsed if parsed is not None else Card(number, colour)


THULLA_P_THRESHOLD = 0.5
DEFAULT_MC_SAMPLES = 200
LOOKAHEAD_SAMPLES = 32
LOOKAHEAD_MAX_UNKNOWN = 28


def choose_computer_card(hand, moves, expected_cards, view, samples=DEFAULT_MC_SAMPLES):
    if not moves:
        raise ValueError("no legal moves")
    if view is None:
        return random.choice(moves)

    must_follow = bool(expected_cards) and any(card in expected_cards for card in hand)
    if expected_cards is None:
        return _choose_lead(hand, moves, view, samples=samples)
    if must_follow:
        return _choose_follow(hand, moves, view, samples=samples)
    return _choose_thulla(hand, moves, view)


def _choose_lead(hand, moves, view, samples=DEFAULT_MC_SAMPLES):
    seats = view.players_after_me_this_trick()
    if not seats:
        seats = [p for p in view.active_indices if p != view.me]

    by_suit = {}
    for card in moves:
        by_suit.setdefault(card.colour, []).append(card)

    p_cache = {}

    def suit_p(suit):
        if suit in p_cache:
            return p_cache[suit]
        if any(view.is_void(p, suit) for p in seats):
            p_cache[suit] = 1.0
            return 1.0
        p = view.estimate_thulla_prob(suit, hand, seats_after=seats, samples=samples)
        p_cache[suit] = p
        return p

    no_void = [s for s in by_suit if not any(view.is_void(p, s) for p in seats)]
    candidates = no_void if no_void else list(by_suit)

    def suit_key(s):
        p = suit_p(s)
        # Prefer low thulla risk; among safe suits prefer dumping A/K.
        if p < THULLA_P_THRESHOLD:
            best_liab = max(_liability_score(c) for c in by_suit[s])
            return (round(p, 1), -best_liab, min(by_suit[s]))
        return (p, 0, min(by_suit[s]))

    best_suit = min(candidates, key=suit_key)
    p = suit_p(best_suit)
    cards = by_suit[best_suit]

    if p >= THULLA_P_THRESHOLD:
        choice = min(cards)
    else:
        choice = max(cards, key=lambda c: (_liability_score(c), c))

    if len(moves) > 1:
        unknown = count_free_unknown(view, hand)
        if unknown <= LOOKAHEAD_MAX_UNKNOWN:
            lead_opts = list({choice, max(cards), min(cards)})
            for s in candidates:
                lead_opts.append(max(by_suit[s], key=lambda c: (_liability_score(c), c)))
            lead_opts = [c for c in dict.fromkeys(lead_opts) if c in moves]
            rates = estimate_lead_lose_rates(
                view, hand, lead_opts, samples=LOOKAHEAD_SAMPLES
            )
            if rates:
                choice = min(
                    lead_opts,
                    key=lambda c: (
                        rates.get(c, 1.0),
                        -_liability_score(c),
                        -NUMBER_CARDS.index(c.number),
                    ),
                )
    return choice


def _choose_follow(hand, moves, view, samples=DEFAULT_MC_SAMPLES):
    suit = moves[0].colour
    seats = view.players_after_me_this_trick()
    p = view.estimate_thulla_prob(suit, hand, seats_after=seats, samples=samples)
    highest = view.current_highest

    if p >= THULLA_P_THRESHOLD and highest is not None:
        under = [card for card in moves if card < highest]
        choice = max(under) if under else min(moves)
    elif highest is not None and len(hand) > 2:
        under = [card for card in moves if card < highest]
        if under:
            # Soft follow: dump high without taking the lead.
            choice = max(under)
        else:
            choice = max(moves, key=lambda c: (_liability_score(c), c))
    else:
        choice = max(moves, key=lambda c: (_liability_score(c), c))

    if (
        len(hand) == 1
        and p >= THULLA_P_THRESHOLD
        and highest is not None
        and choice > highest
    ):
        under = [card for card in moves if card < highest]
        if under:
            return max(under)
    return choice


def _choose_thulla(hand, moves, view):
    victim = view.current_highest_player
    if victim is not None:
        punish = [card for card in moves if view.is_void(victim, card.colour)]
        if punish:
            return max(punish, key=lambda c: (_liability_score(c), c))
    liabilities = [c for c in moves if _liability_score(c) > 0]
    if liabilities:
        return max(liabilities, key=lambda c: (_liability_score(c), c))
    counts = {}
    for card in hand:
        counts[card.colour] = counts.get(card.colour, 0) + 1
    short = [card for card in moves if counts.get(card.colour, 0) <= 2]
    if short:
        return random.choice(short)
    return max(moves)


def should_cpu_take(hand, view, neighbor_idx, i_am_leader, allow_late_take=True):
    if view is None or neighbor_idx is None:
        return False
    active_n = len(view.active_indices)
    if active_n <= 2:
        return False
    if not i_am_leader:
        return False
    if case_a_should_take(view, hand, neighbor_idx):
        if active_n == 3 and count_free_unknown(view, hand) <= 8:
            others = [p for p in view.active_indices if p != view.me and p != neighbor_idx]
            if len(others) == 1:
                lose_keep, lose_merge = compare_take_lose_rates(
                    view, hand, neighbor_idx, others[0], samples=40
                )
                return lose_merge + 0.1 < lose_keep
        return True
    if not allow_late_take:
        return False
    if active_n == 3 and count_free_unknown(view, hand) <= 8:
        others = [p for p in view.active_indices if p != view.me and p != neighbor_idx]
        if len(others) != 1:
            return False
        lose_keep, lose_merge = compare_take_lose_rates(
            view, hand, neighbor_idx, others[0], samples=40
        )
        return lose_merge + 0.1 < lose_keep
    return False


class ComputerPlayer(BasePlayer):
    def __init__(self, name, mc_samples=DEFAULT_MC_SAMPLES, allow_late_take=True):
        super().__init__(name)
        self.mc_samples = mc_samples
        self.allow_late_take = allow_late_take

    def play_turn(self, expected_cards, view=None):
        moves = valid_moves(self.hand, expected_cards)
        card = choose_computer_card(
            self.hand, moves, expected_cards, view, samples=self.mc_samples
        )
        self.hand.remove(card)
        return card

    def offer_take(self, target_name, n_cards, view=None, neighbor_idx=None, i_am_leader=False):
        return should_cpu_take(
            self.hand,
            view,
            neighbor_idx,
            i_am_leader,
            allow_late_take=self.allow_late_take,
        )


class RandomPlayer(BasePlayer):
    def play_turn(self, expected_cards, view=None):
        moves = valid_moves(self.hand, expected_cards)
        card = random.choice(moves)
        self.hand.remove(card)
        return card

    def offer_take(self, target_name, n_cards, view=None, neighbor_idx=None, i_am_leader=False):
        return False


class ScriptedPlayer(BasePlayer):
    """Deterministic player for tests: queued cards and optional take/give answers."""

    def __init__(self, name, take_decisions=None, give_decisions=None):
        super().__init__(name)
        self.play_queue = []
        self.take_decisions = list(take_decisions or [])
        self.give_decisions = list(give_decisions or [])

    def queue_plays(self, cards):
        self.play_queue.extend(cards)

    def offer_take(self, target_name, n_cards, view=None, neighbor_idx=None, i_am_leader=False):
        if not self.take_decisions:
            return False
        return bool(self.take_decisions.pop(0))

    def offer_give(self, asker_name, n_cards, view=None, asker_idx=None):
        if not self.give_decisions:
            return True
        return bool(self.give_decisions.pop(0))

    def play_turn(self, expected_cards, view=None):
        if not self.play_queue:
            raise RuntimeError(f"{self.name} has no scripted card to play")
        card = self.play_queue.pop(0)
        moves = valid_moves(self.hand, expected_cards)
        if card not in moves:
            raise ValueError(f"{self.name} scripted illegal card {card}; legal: {moves}")
        self.hand.remove(card)
        return card
