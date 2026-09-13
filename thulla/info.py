from .cards import Card, cards_of_suit, create_deck


class PlayerView:
    """Read-only snapshot for one player. Never includes other hidden hands."""

    def __init__(self, info, me, remaining_after):
        self._info = info
        self.me = me
        self._remaining_after = list(remaining_after)

    @property
    def active_indices(self):
        return list(self._info.active_indices)

    @property
    def player_cnt(self):
        return self._info.player_cnt

    def hand_size(self, player_idx):
        return self._info.hand_sizes[player_idx]

    def is_void(self, player_idx, suit):
        return suit in self._info.voids.get(player_idx, set())

    def players_after_me_this_trick(self):
        return list(self._remaining_after)

    @property
    def current_highest(self):
        return self._info.current_highest

    @property
    def current_highest_player(self):
        return self._info.current_highest_player

    def known_cards(self, player_idx):
        """Hard public holdings only (thulla pickup / take). See visible_cards for 1v1."""
        return set(self._info.known_holdings.get(player_idx, set()))

    def heads_up_opponent(self):
        """Sole other active seat when exactly two remain and I am one of them."""
        active = self.active_indices
        if len(active) != 2 or self.me not in active:
            return None
        for p in active:
            if p != self.me:
                return p
        return None

    def deduced_hand(self, player_idx, my_hand):
        """
        Full hand of player_idx if uniquely determined from public facts + my_hand.

        Heads-up only: with one opponent, every remaining free card must be theirs
        (deck − discarded − my hand − known holdings − current trick). Returns None
        if not heads-up or counts do not line up (e.g. mid-inconsistency).
        Does not read other hidden hands — viewer-relative deduction only.
        """
        if player_idx == self.me:
            return set(my_hand)
        opp = self.heads_up_opponent()
        if opp is None or player_idx != opp:
            return None
        known = self.known_cards(player_idx)
        free = self._unassigned_cards(my_hand)
        for card in free:
            if self.cannot_hold(player_idx, card):
                return None
        full = known | set(free)
        if len(full) != self.hand_size(player_idx):
            return None
        return full

    def visible_cards(self, player_idx, my_hand):
        """Hard known holdings, plus complete-info deduction when available."""
        deduced = self.deduced_hand(player_idx, my_hand)
        if deduced is not None:
            return set(deduced)
        return self.known_cards(player_idx)

    def cards_played_by(self, player_idx):
        """All cards this seat has played so far (public history)."""
        return list(self._info.played_by.get(player_idx, []))

    def highest_played_of_suit(self, player_idx, suit):
        """Highest card of `suit` this player has ever played (factual)."""
        return self._info.highest_played.get(player_idx, {}).get(suit)

    def under_ceiling(self, player_idx, suit):
        """
        Soft duck inference: if this seat followed under the then-leader,
        returns (played, ceiling). Convention says they likely hold no card C
        with played < C < ceiling — but they may be sandbagging.
        """
        return self._info.under_ceilings.get(player_idx, {}).get(suit)

    def publicly_accounted(self):
        """Cards whose location is already known (discarded, trick, or known holdings)."""
        seen = set(self._info.discarded)
        seen.update(self._info.trick_cards)
        for cards in self._info.known_holdings.values():
            seen.update(cards)
        return seen

    def duck_gap_unknowns(self, player_idx, suit):
        """
        Still-unknown ranks strictly between a duck play and its ceiling.
        Skips cards already in discards / trick / known holdings — those are
        facts, not soft hints (e.g. Q under A should not imply 'no K' once K
        was also played on the trick).
        """
        under = self.under_ceiling(player_idx, suit)
        if under is None:
            return []
        lo, hi = under
        accounted = self.publicly_accounted()
        return [c for c in cards_of_suit(suit) if lo < c < hi and c not in accounted]

    def cannot_hold(self, player_idx, card):
        """True only for hard public facts (suit voids). Soft duck/suit-high
        inferences belong in unlikely_hold — never treat those as proofs."""
        return card.colour in self._info.voids.get(player_idx, set())

    def unlikely_hold(self, player_idx, card):
        """
        Soft play-convention hints (not proofs):
        - ducked under the leader → likely no middle cards between play and ceiling
        - took/kept lead in-suit → likely no higher of that suit left
        Players can sandbag; do not use as hard deal bans.
        Already-public cards (discarded / trick / known) are never flagged.
        """
        if card in self.publicly_accounted():
            return False
        under = self.under_ceiling(player_idx, card.colour)
        if under is not None:
            played, ceiling = under
            if played < card < ceiling:
                return True
        shown = self._info.suit_high_shown.get(player_idx, {}).get(card.colour)
        if shown is not None and card > shown:
            return True
        return False

    def unknown_slots(self, player_idx, my_hand=None):
        if my_hand is not None and self.deduced_hand(player_idx, my_hand) is not None:
            return 0
        known_n = len(self.known_cards(player_idx))
        return max(0, self.hand_size(player_idx) - known_n)

    def unseen_of(self, suit, my_hand):
        seen = set(self._info.discarded)
        seen.update(c for c in my_hand if c.colour == suit)
        for p in self.active_indices:
            if p == self.me:
                continue
            seen.update(c for c in self.visible_cards(p, my_hand) if c.colour == suit)
        seen.update(c for c in self._info.trick_cards if c.colour == suit)
        return set(cards_of_suit(suit)) - seen

    def _unassigned_cards(self, my_hand):
        """Cards not in discarded, my hand, hard known holdings, or current trick."""
        seen = set(self._info.discarded)
        seen.update(my_hand)
        for cards in self._info.known_holdings.values():
            seen.update(cards)
        seen.update(self._info.trick_cards)
        return [c for c in create_deck() if c not in seen]

    def free_cards(self, my_hand):
        """Unknown cards still to assign across opponents (empty under heads-up complete info)."""
        free = self._unassigned_cards(my_hand)
        opp = self.heads_up_opponent()
        if opp is not None and self.deduced_hand(opp, my_hand) is not None:
            return []
        return free

    def estimate_thulla_prob(self, suit, my_hand, seats_after=None, samples=200):
        from .prob import estimate_thulla_prob

        seats = self.players_after_me_this_trick() if seats_after is None else seats_after
        return estimate_thulla_prob(self, suit, my_hand, seats, samples=samples)


class PublicInfo:
    def __init__(self, player_cnt):
        self.player_cnt = player_cnt
        self.reset(list(range(player_cnt)))

    def reset(self, active_indices):
        self.active_indices = list(active_indices)
        self.discarded = set()
        self.known_holdings = {i: set() for i in range(self.player_cnt)}
        self.voids = {i: set() for i in range(self.player_cnt)}
        self.hand_sizes = [0] * self.player_cnt
        # Per-player play history + suit inferences for the bot.
        self.played_by = {i: [] for i in range(self.player_cnt)}
        # Factual: highest card of each suit this seat has played.
        self.highest_played = {i: {} for i in range(self.player_cnt)}
        # Soft inference: seat played their suit-high (lead or take-lead).
        self.suit_high_shown = {i: {} for i in range(self.player_cnt)}
        # suit -> (played_under, then_ceiling): soft duck hint, not a proof.
        self.under_ceilings = {i: {} for i in range(self.player_cnt)}
        self._clear_trick()

    def sync_hands(self, players):
        self.hand_sizes = [len(p.hand) for p in players]

    def _clear_trick(self):
        self.led_suit = None
        self.current_highest = None
        self.current_highest_player = None
        self.trick_cards = []

    def view_for(self, me, remaining_after):
        return PlayerView(self, me, remaining_after)

    def _note_suit_inferences(self, player_idx, card, led_suit, prior_highest):
        """
        Track who played what, plus follow/lead inferences:
        - Duck under the leader → played their highest under that card.
        - Lead or take the lead in-suit → soft "suit-high" (no higher left).
        """
        self.played_by[player_idx].append(card)

        prev_high = self.highest_played[player_idx].get(card.colour)
        if prev_high is None or card > prev_high:
            self.highest_played[player_idx][card.colour] = card

        if led_suit is None:
            # Opening lead: keep factual highest_played only.
            # Soft suit-high would be wrong when bots lead low under thulla risk.
            return

        if card.colour != led_suit:
            return

        if prior_highest is not None and card < prior_highest:
            # Followed under the current winner: soft highest-under convention
            # (players may sandbag — do not treat as a hard void of the gap).
            prev = self.under_ceilings[player_idx].get(led_suit)
            lo, hi = card, prior_highest
            if prev is not None:
                # Intersection of duck hints (tightest observed bounds).
                lo = max(lo, prev[0])
                hi = min(hi, prev[1])
            if lo < hi:
                self.under_ceilings[player_idx][led_suit] = (lo, hi)
            return

        # Took / kept the lead in-suit: soft suit-high convention.
        shown = self.suit_high_shown[player_idx].get(led_suit)
        if shown is None or card > shown:
            self.suit_high_shown[player_idx][led_suit] = card

    def note_play(self, player_idx, card, led_suit):
        prior_highest = self.current_highest
        self.known_holdings[player_idx].discard(card)
        if card.colour in self.voids[player_idx]:
            self.voids[player_idx].discard(card.colour)
        if led_suit and card.colour != led_suit:
            self.voids[player_idx].add(led_suit)

        self._note_suit_inferences(player_idx, card, led_suit, prior_highest)

        if led_suit is None:
            self.led_suit = card.colour
            self.current_highest = card
            self.current_highest_player = player_idx
        else:
            self.led_suit = led_suit
            if card.colour == led_suit and (
                self.current_highest is None or card > self.current_highest
            ):
                self.current_highest = card
                self.current_highest_player = player_idx

        self.trick_cards.append(card)
        if self.hand_sizes[player_idx] > 0:
            self.hand_sizes[player_idx] -= 1

    def finish_clean(self, cards):
        self.discarded.update(cards)
        self._clear_trick()

    def finish_thulla(self, victim_idx, cards):
        for card in cards:
            self.known_holdings[victim_idx].add(card)
            self.voids[victim_idx].discard(card.colour)
            # Pickup can restore higher cards than a prior "shown high".
            shown = self.suit_high_shown[victim_idx].get(card.colour)
            if shown is not None and card > shown:
                del self.suit_high_shown[victim_idx][card.colour]
            under = self.under_ceilings[victim_idx].get(card.colour)
            if under is not None:
                lo, hi = under
                if lo < card < hi:
                    del self.under_ceilings[victim_idx][card.colour]
        self.hand_sizes[victim_idx] += len(cards)
        self._clear_trick()

    def note_take(self, taker_idx, target_idx, cards):
        known = set(self.known_holdings[target_idx])
        self.known_holdings[taker_idx].update(known)
        for card in known:
            self.voids[taker_idx].discard(card.colour)
            shown = self.suit_high_shown[taker_idx].get(card.colour)
            if shown is not None and card > shown:
                del self.suit_high_shown[taker_idx][card.colour]
            under = self.under_ceilings[taker_idx].get(card.colour)
            if under is not None:
                lo, hi = under
                if lo < card < hi:
                    del self.under_ceilings[taker_idx][card.colour]
        self.known_holdings[target_idx].clear()
        self.voids[target_idx].clear()
        self.suit_high_shown[target_idx].clear()
        self.under_ceilings[target_idx].clear()
        n = len(cards)
        self.hand_sizes[taker_idx] += n
        self.hand_sizes[target_idx] = 0

    def note_got_away(self, idx):
        if idx in self.active_indices:
            self.active_indices.remove(idx)
