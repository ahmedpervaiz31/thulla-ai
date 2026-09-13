import random

from .cards import (
    Card,
    NUMBER_CARDS,
    parse_card,
    valid_moves,
    format_hand,
    format_cards,
    raise_equivalence,
)
from .prob import (
    TAKE_MARGIN,
    TAKE_MARGIN_SAFE_FACE,
    TAKE_UNKNOWN_MAX,
    compare_take_lose_rates,
    count_free_unknown,
    dump_tier,
    dump_value,
    estimate_lead_lose_rates,
    follow_take_safe,
    has_dump_safe_face_lead,
    is_face,
    is_keeper,
    suit_dump_safe,
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


def _equiv_accounted(hand, view):
    if view is None:
        return set(hand)
    return set(hand) | view.publicly_accounted()


def _play_equiv(card, hand, moves, view):
    return raise_equivalence(card, hand, moves, accounted=_equiv_accounted(hand, view))


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

    safe_suits = [
        s
        for s in candidates
        if suit_dump_safe(view, hand, s, seats, p_thulla=suit_p(s), threshold=THULLA_P_THRESHOLD)
    ]

    def best_in_suit(s):
        return max(by_suit[s], key=lambda c: (dump_tier(c), dump_value(c), c))

    def low_in_suit(s):
        cards = by_suit[s]
        non_keepers = [c for c in cards if not is_keeper(c)]
        pool = non_keepers if non_keepers else cards
        return min(pool)

    if safe_suits:
        def suit_key(s):
            best = best_in_suit(s)
            return (-dump_tier(best), len(by_suit[s]), -dump_value(best))

        best_suit = min(safe_suits, key=suit_key)
        choice = best_in_suit(best_suit)
    else:
        def risk_key(s):
            return (suit_p(s), len(by_suit[s]), min(by_suit[s]))

        best_suit = min(candidates, key=risk_key)
        p = suit_p(best_suit)
        if p >= THULLA_P_THRESHOLD:
            choice = low_in_suit(best_suit)
        else:
            choice = best_in_suit(best_suit)

    # Never lead a keeper while any mid/face lead exists.
    high_tier = [c for c in moves if dump_tier(c) >= 1]
    if high_tier and dump_tier(choice) == 0:
        safe_high = [c for c in high_tier if c.colour in safe_suits]
        pool = safe_high if safe_high else high_tier
        choice = max(
            pool,
            key=lambda c: (dump_tier(c), -len(by_suit[c.colour]), dump_value(c), c),
        )

    choice = _play_equiv(choice, hand, moves, view)

    if len(moves) > 1:
        unknown = count_free_unknown(view, hand)
        if unknown <= LOOKAHEAD_MAX_UNKNOWN:
            lead_opts = [choice, low_in_suit(best_suit), best_in_suit(best_suit)]
            for s in candidates:
                lead_opts.append(best_in_suit(s))
                lead_opts.append(low_in_suit(s))
            lead_opts.extend(high_tier)
            lead_opts = [
                _play_equiv(c, hand, moves, view)
                for c in dict.fromkeys(lead_opts)
                if c in moves
            ]
            lead_opts = list(dict.fromkeys(lead_opts))
            if any(dump_tier(c) >= 1 for c in lead_opts):
                lead_opts = [c for c in lead_opts if dump_tier(c) >= 1] or lead_opts
            rates = estimate_lead_lose_rates(
                view, hand, lead_opts, samples=LOOKAHEAD_SAMPLES
            )
            if rates:
                choice = min(
                    lead_opts,
                    key=lambda c: (
                        rates.get(c, 1.0),
                        -dump_tier(c),
                        -dump_value(c),
                        -NUMBER_CARDS.index(c.number),
                    ),
                )
    return _play_equiv(choice, hand, moves, view)


def _choose_follow(hand, moves, view, samples=DEFAULT_MC_SAMPLES):
    suit = moves[0].colour
    seats = view.players_after_me_this_trick()
    p = view.estimate_thulla_prob(suit, hand, seats_after=seats, samples=samples)
    highest = view.current_highest
    winners = [c for c in moves if highest is None or c > highest]
    under = [c for c in moves if highest is not None and c < highest]
    take_ok = follow_take_safe(
        view, hand, suit, seats, p_thulla=p, threshold=THULLA_P_THRESHOLD
    )
    face_winners = [c for c in winners if is_face(c)]

    if p >= THULLA_P_THRESHOLD and highest is not None:
        if under:
            choice = max(under, key=lambda c: (dump_tier(c), dump_value(c), c))
        else:
            choice = min(moves)
    elif face_winners and take_ok:
        choice = max(face_winners, key=lambda c: (dump_value(c), c))
    elif winners and take_ok:
        choice = max(winners, key=lambda c: (dump_tier(c), dump_value(c), c))
    elif under:
        choice = max(under, key=lambda c: (dump_tier(c), dump_value(c), c))
    elif winners:
        choice = min(winners)
    else:
        choice = max(moves, key=lambda c: (dump_tier(c), dump_value(c), c))

    if (
        len(hand) == 1
        and p >= THULLA_P_THRESHOLD
        and highest is not None
        and choice > highest
    ):
        if under:
            choice = max(under, key=lambda c: (dump_tier(c), dump_value(c), c))
    return _play_equiv(choice, hand, moves, view)


def _choose_thulla(hand, moves, view):
    victim = view.current_highest_player
    if victim is not None:
        punish = [card for card in moves if view.is_void(victim, card.colour)]
        if punish:
            return _play_equiv(
                max(punish, key=lambda c: (dump_tier(c), dump_value(c), c)),
                hand,
                moves,
                view,
            )
    faces = [c for c in moves if is_face(c)]
    if faces:
        return _play_equiv(
            max(faces, key=lambda c: (dump_value(c), c)),
            hand,
            moves,
            view,
        )
    counts = {}
    for card in hand:
        counts[card.colour] = counts.get(card.colour, 0) + 1
    non_keepers = [c for c in moves if not is_keeper(c)]
    pool = non_keepers if non_keepers else list(moves)
    short = [card for card in pool if counts.get(card.colour, 0) <= 2]
    if short:
        return _play_equiv(
            max(short, key=lambda c: (dump_tier(c), dump_value(c), c)),
            hand,
            moves,
            view,
        )
    return _play_equiv(
        max(pool, key=lambda c: (dump_tier(c), dump_value(c), c)),
        hand,
        moves,
        view,
    )


def should_cpu_take(hand, view, neighbor_idx, i_am_leader, allow_late_take=True):
    """Take only when merge clearly lowers P(finish last)."""
    if view is None or neighbor_idx is None:
        return False
    active_n = len(view.active_indices)
    if active_n <= 2:
        return False
    if not i_am_leader:
        return False
    if not allow_late_take:
        return False
    if count_free_unknown(view, hand) > TAKE_UNKNOWN_MAX:
        return False

    lose_keep, lose_merge = compare_take_lose_rates(
        view, hand, neighbor_idx, samples=40
    )
    margin = (
        TAKE_MARGIN_SAFE_FACE
        if has_dump_safe_face_lead(view, hand)
        else TAKE_MARGIN
    )
    return lose_merge + margin < lose_keep


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
