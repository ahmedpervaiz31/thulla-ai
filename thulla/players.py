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
from .heads_up import try_exact_from_view
from .prob import (
    TAKE_MARGIN,
    TAKE_MARGIN_SAFE_FACE,
    TAKE_UNKNOWN_MAX,
    THULLA_MC_MAX_CANDIDATES,
    compare_take_lose_rates,
    count_free_unknown,
    dump_tier,
    dump_value,
    follow_take_safe,
    has_dump_safe_face_lead,
    immediate_self_thulla_prob,
    is_face,
    is_keeper,
    LOOKAHEAD_SAMPLES,
    score_lead_candidates,
    score_thulla_candidates,
    shortlist_thulla_candidates,
    suit_dump_safe,
    thulla_dump_score_key,
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
LOOKAHEAD_MAX_UNKNOWN = 52
# Cap MC lead options early/mid (full hand still uses heuristic shortlist).
LEAD_MC_MAX_CANDIDATES = 4


def _lead_mc_samples(unknown):
    """Fewer deal samples when the unknown pool is large (early/mid game)."""
    if unknown <= 12:
        return LOOKAHEAD_SAMPLES
    if unknown <= 24:
        return 24
    if unknown <= 36:
        return 16
    return 12


def _thulla_mc_samples(unknown):
    """Dump MC budget — never reuse the 200 void-estimate sample count.

    Horizon-only rollouts early; a bit more when full lose-rate is on.
    """
    if unknown <= 12:
        return 24
    if unknown <= 20:
        return 16
    if unknown <= 36:
        return 12
    return 8


def _lead_mc_shortlist(lead_opts, view, max_n=LEAD_MC_MAX_CANDIDATES):
    """Keep MC cheap: prefer low-void suits, diversify suits, then dump tier."""
    if len(lead_opts) <= max_n:
        return list(lead_opts)
    seats = view.players_after_me_this_trick()
    if not seats:
        seats = [p for p in view.active_indices if p != view.me]

    def void_count(card):
        return sum(1 for p in seats if view.is_void(p, card.colour))

    ranked = sorted(
        lead_opts,
        key=lambda c: (void_count(c), -dump_tier(c), -dump_value(c), c.code()),
    )
    picked = []
    seen_suits = set()
    for card in ranked:
        if card.colour in seen_suits:
            continue
        picked.append(card)
        seen_suits.add(card.colour)
        if len(picked) >= max_n:
            return picked
    for card in ranked:
        if card in picked:
            continue
        picked.append(card)
        if len(picked) >= max_n:
            break
    return picked


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

    exact = try_exact_from_view(hand, moves, expected_cards, view)
    if exact is not None:
        return exact

    must_follow = bool(expected_cards) and any(card in expected_cards for card in hand)
    if expected_cards is None:
        return _choose_lead(hand, moves, view, samples=samples)
    if must_follow:
        return _choose_follow(hand, moves, view, samples=samples)
    return _choose_thulla(hand, moves, view, samples=samples)


def _lead_score_key(card, scores, pickups=None):
    """Lower is better. On equal score prefer low self-thulla, then low dump tier."""
    pickup = 0.0 if not pickups else pickups.get(card, 0.0)
    return (
        scores.get(card, 1.0),
        pickup,
        dump_tier(card),
        dump_value(card),
        -NUMBER_CARDS.index(card.number),
    )


def _choose_lead(hand, moves, view, samples=DEFAULT_MC_SAMPLES):
    lead_opts = list(
        dict.fromkeys(_play_equiv(c, hand, moves, view) for c in moves)
    )

    unknown = count_free_unknown(view, hand)
    if len(lead_opts) > 1 and unknown <= LOOKAHEAD_MAX_UNKNOWN:
        shortlist = _lead_mc_shortlist(lead_opts, view)
        scores, _, pickups = score_lead_candidates(
            view, hand, shortlist, samples=_lead_mc_samples(unknown)
        )
        if scores:
            choice = min(
                shortlist, key=lambda c: _lead_score_key(c, scores, pickups)
            )
            return _play_equiv(choice, hand, moves, view)

    return _choose_lead_heuristic(hand, moves, view, samples=samples)


def _choose_lead_heuristic(hand, moves, view, samples=DEFAULT_MC_SAMPLES):
    """Fallback lead when too many unknowns for full MC scoring."""
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

    def void_count_after(suit):
        return sum(1 for p in seats if view.is_void(p, suit))

    candidates = list(by_suit)

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
            return (suit_p(s), void_count_after(s), len(by_suit[s]), min(by_suit[s]))

        best_suit = min(candidates, key=risk_key)
        p = suit_p(best_suit)
        if p >= THULLA_P_THRESHOLD:
            choice = low_in_suit(best_suit)
        else:
            choice = best_in_suit(best_suit)

    choice = _play_equiv(choice, hand, moves, view)

    if len(moves) > 1:
        all_opts = list(
            dict.fromkeys(_play_equiv(c, hand, moves, view) for c in moves)
        )
        pickups = {
            c: immediate_self_thulla_prob(
                view, hand, c, seats_after=seats, samples=16
            )
            for c in all_opts
        }
        if any(p < THULLA_P_THRESHOLD for p in pickups.values()):
            choice = min(
                all_opts,
                key=lambda c: (
                    void_count_after(c.colour),
                    suit_p(c.colour),
                    pickups[c],
                    -dump_tier(c),
                    -dump_value(c),
                    c,
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


def _choose_thulla(hand, moves, view, samples=None):
    """Dump via MC lose-rate + short-horizon victim-escape pressure."""
    opts = list(dict.fromkeys(_play_equiv(c, hand, moves, view) for c in moves))
    if not opts:
        raise ValueError("no legal thulla dumps")
    if len(opts) == 1:
        return opts[0]

    unknown = count_free_unknown(view, hand)
    # Ignore the void-estimate sample count (often 200) — dump MC has its own budget.
    n_samples = _thulla_mc_samples(unknown)
    if samples is not None:
        n_samples = min(n_samples, max(8, samples))
    shortlist = shortlist_thulla_candidates(
        view, hand, opts, max_n=THULLA_MC_MAX_CANDIDATES
    )
    scores, _, extras = score_thulla_candidates(
        view, hand, shortlist, samples=n_samples
    )
    choice = min(shortlist, key=lambda c: thulla_dump_score_key(c, scores, extras))
    return _play_equiv(choice, hand, moves, view)


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
