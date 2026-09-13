import random

from .cards import NUMBER_CARDS, raise_equivalence

KEEPER_RANKS = frozenset({"2", "3", "4", "5"})
MID_RANKS = frozenset({"6", "7", "8", "9", "10"})
FACE_DUMP_VALUES = {"A": 10, "K": 9, "Q": 8, "J": 7}
MID_DUMP_VALUES = {"10": 5, "9": 4, "8": 3, "7": 2, "6": 1}
KEEPER_DUMP_VALUES = {"5": -1, "4": -2, "3": -3, "2": -4}
LONG_SUIT_LEN = 4
HEAVY_DISCARD_COUNT = 6
DUMP_SAFE_P_THRESHOLD = 0.5
TAKE_UNKNOWN_MAX = 20
TAKE_MARGIN = 0.1
TAKE_MARGIN_SAFE_FACE = 0.15


def is_keeper(card):
    return card.number in KEEPER_RANKS


def is_mid(card):
    return card.number in MID_RANKS


def is_face(card):
    return card.number in FACE_DUMP_VALUES


def dump_tier(card):
    """2 = face, 1 = mid (6–10), 0 = keeper (2–5)."""
    if card.number in FACE_DUMP_VALUES:
        return 2
    if card.number in MID_RANKS:
        return 1
    return 0


def dump_value(card):
    """Higher = prefer dumping. Faces > mids > keepers."""
    if card.number in FACE_DUMP_VALUES:
        return FACE_DUMP_VALUES[card.number]
    if card.number in MID_DUMP_VALUES:
        return MID_DUMP_VALUES[card.number]
    if card.number in KEEPER_DUMP_VALUES:
        return KEEPER_DUMP_VALUES[card.number]
    return 0


def _liability_score(card):
    """Alias for dump_value (compat with older call sites / tests)."""
    return dump_value(card)


def suit_length(hand, suit):
    return sum(1 for c in hand if c.colour == suit)


def discarded_of_suit(view, suit):
    return sum(1 for c in view._info.discarded if c.colour == suit)


def suit_dump_safe(view, hand, suit, seats_after, p_thulla=None, threshold=DUMP_SAFE_P_THRESHOLD):
    """True when *leading* a face in `suit` is acceptable (shape + void risk)."""
    seats = list(seats_after or [])
    if any(view.is_void(p, suit) for p in seats):
        return False
    if p_thulla is None:
        p_thulla = estimate_thulla_prob(view, suit, hand, seats_after=seats)
    if p_thulla >= threshold:
        return False
    length = suit_length(hand, suit)
    if length >= LONG_SUIT_LEN:
        return False
    if discarded_of_suit(view, suit) >= HEAVY_DISCARD_COUNT and length >= 3:
        return False
    return True


def follow_take_safe(view, hand, suit, seats_after, p_thulla=None, threshold=DUMP_SAFE_P_THRESHOLD):
    """True when *winning* the trick on follow is acceptable (void risk only).

    Length / heavy-discard are lead-shape concerns and must not block cashing A/K/Q/J.
    """
    seats = list(seats_after or [])
    if any(view.is_void(p, suit) for p in seats):
        return False
    if p_thulla is None:
        p_thulla = estimate_thulla_prob(view, suit, hand, seats_after=seats)
    return p_thulla < threshold


def has_dump_safe_face_lead(view, hand, seats_after=None, samples=200):
    """True if we can still lead a face in a dump-safe suit (survive another round)."""
    seats = list(seats_after) if seats_after is not None else [
        p for p in view.active_indices if p != view.me
    ]
    by_suit = {}
    for c in hand:
        by_suit.setdefault(c.colour, []).append(c)
    for suit, cards in by_suit.items():
        if not any(is_face(c) for c in cards):
            continue
        if any(view.is_void(p, suit) for p in seats):
            continue
        p = estimate_thulla_prob(view, suit, hand, seats_after=seats, samples=samples)
        if suit_dump_safe(view, hand, suit, seats, p_thulla=p):
            return True
    return False


def estimate_thulla_prob(view, suit, my_hand, seats_after, samples=200):
    """P(someone in seats_after cannot follow suit)."""
    seats = list(seats_after)
    if not seats:
        return 0.0
    if any(view.is_void(p, suit) for p in seats):
        return 1.0

    max_copies = len(view.unseen_of(suit, my_hand))
    for p in seats:
        max_copies += sum(1 for c in view.visible_cards(p, my_hand) if c.colour == suit)
    if len(seats) > max_copies:
        return 1.0

    if all(any(c.colour == suit for c in view.visible_cards(p, my_hand)) for p in seats):
        if not any(c.colour == suit for c in view.free_cards(my_hand)):
            return 0.0

    hits = 0
    for dealt in _sample_deals(view, my_hand, samples):
        if _someone_void(dealt, view, seats, suit, my_hand):
            hits += 1
    return hits / max(1, samples)


def _someone_void(dealt, view, seats, suit, my_hand):
    for p in seats:
        if view.is_void(p, suit):
            return True
        has = any(c.colour == suit for c in view.visible_cards(p, my_hand))
        has = has or any(c.colour == suit for c in dealt.get(p, []))
        if not has:
            return True
    return False


def _sample_deals(view, my_hand, samples):
    others = [p for p in view.active_indices if p != view.me]
    slots = {p: view.unknown_slots(p, my_hand) for p in others}
    total_slots = sum(slots.values())
    free = list(view.free_cards(my_hand))
    void_masks = {p: set(view._info.voids.get(p, set())) for p in others}
    # Hard bans only (suit voids via cannot_hold). Soft duck / suit-high
    # hints must not erase cards from the deal pool — sandbagging is legal.
    banned = {
        p: {c for c in free if view.cannot_hold(p, c)} for p in others
    }

    if total_slots <= 0:
        empty = {p: [] for p in others}
        for _ in range(samples):
            yield empty
        return

    for _ in range(samples):
        if len(free) > total_slots:
            pool = random.sample(free, total_slots)
        else:
            pool = list(free)
        yield _deal_once(others, slots, pool, void_masks, banned)


def _deal_once(others, slots, pool, void_masks, banned=None):
    banned = banned or {}
    random.shuffle(pool)
    dealt = {p: [] for p in others}
    remaining = list(pool)

    # First pass: only legal (non-void / non-banned) assignments
    still = []
    for card in remaining:
        placed = False
        candidates = [
            p
            for p in others
            if len(dealt[p]) < slots[p]
            and card.colour not in void_masks[p]
            and card not in banned.get(p, ())
        ]
        if candidates:
            # Fill players with most remaining need first for stability
            candidates.sort(key=lambda p: slots[p] - len(dealt[p]), reverse=True)
            dealt[candidates[0]].append(card)
            placed = True
        if not placed:
            still.append(card)

    # Second pass: force-fill if constraints were over-tight
    for card in still:
        for p in others:
            if len(dealt[p]) < slots[p]:
                dealt[p].append(card)
                break
    return dealt


def count_free_unknown(view, my_hand):
    return len(view.free_cards(my_hand))


def case_a_should_take(view, my_hand, neighbor_idx):
    """Conservative merge signal — one void + a big hand is not enough."""
    n = view.hand_size(neighbor_idx)
    if n >= 5:
        return False

    my_suits = {c.colour for c in my_hand}
    suits = ("Diamond", "Heart", "Spade", "Club")
    useful_voids = [s for s in suits if view.is_void(neighbor_idx, s) and s in my_suits]

    if len(useful_voids) >= 2:
        return True

    if n > 3:
        return False

    if useful_voids:
        return True

    known = list(view.visible_cards(neighbor_idx, my_hand))
    if not known:
        return False
    my_voids = set()
    for s in suits:
        if view.is_void(view.me, s) or not any(c.colour == s for c in my_hand):
            my_voids.add(s)
    hits = sum(1 for c in known if c.colour in my_voids)
    return hits * 2 >= len(known)


def compare_take_lose_rates(view, my_hand, neighbor_idx, samples=40):
    """Return (lose_rate_keep, lose_rate_merge) via N-player survival rollouts."""
    active = list(view.active_indices)
    me = view.me
    if neighbor_idx not in active or me not in active or len(active) < 3:
        return 1.0, 1.0

    others = [p for p in active if p != me]
    lose_keep = 0
    lose_merge = 0
    n = 0
    for dealt in _sample_deals(view, my_hand, samples):
        n += 1
        full = [[] for _ in range(view.player_cnt)]
        full[me] = list(my_hand)
        for p in others:
            known = list(view.visible_cards(p, my_hand))
            sampled = list(dealt.get(p, []))
            full[p] = _pad_hand(known + sampled, view.hand_size(p))

        keep_hands = [list(full[p]) for p in active]
        me_keep = active.index(me)
        if _n_player_i_lose(keep_hands, me_keep, me_keep, use_survival=True):
            lose_keep += 1

        merged_seats = [p for p in active if p != neighbor_idx]
        merge_hands = []
        for p in merged_seats:
            if p == me:
                merge_hands.append(list(my_hand) + list(full[neighbor_idx]))
            else:
                merge_hands.append(list(full[p]))
        me_merge = merged_seats.index(me)
        if _n_player_i_lose(merge_hands, me_merge, me_merge, use_survival=True):
            lose_merge += 1

    if n == 0:
        return 1.0, 1.0
    return lose_keep / n, lose_merge / n


def _pad_hand(cards, size):
    return list(cards)[:size] if len(cards) >= size else list(cards)


def _heads_up_i_lose(my, opp, max_tricks=200):
    me = list(my)
    them = list(opp)
    leader = 0  # 0 = me
    for _ in range(max_tricks):
        if not me:
            return False
        if not them:
            return True
        if leader == 0:
            lead = min(me)
            me.remove(lead)
            resp = _respond(them, lead)
            them.remove(resp)
            if resp.colour != lead.colour:
                me.extend([lead, resp])
                leader = 0
            else:
                leader = 0 if lead > resp else 1
        else:
            lead = min(them)
            them.remove(lead)
            resp = _respond(me, lead)
            me.remove(resp)
            if resp.colour != lead.colour:
                them.extend([lead, resp])
                leader = 1
            else:
                leader = 1 if lead > resp else 0
    return len(me) > 0


def _three_way_i_lose(a, b, c, max_tricks=200):
    return _n_player_i_lose([a, b, c], me_idx=0, leader_idx=0, max_tricks=max_tricks, use_survival=False)


def _survival_lead_card(hand):
    """Lead heuristic for rollouts: highest dump tier, prefer shorter suits."""
    by_suit = {}
    for c in hand:
        by_suit.setdefault(c.colour, []).append(c)

    def best_in_suit(s):
        return max(by_suit[s], key=lambda c: (dump_tier(c), dump_value(c), c))

    def suit_score(s):
        best = best_in_suit(s)
        return (-dump_tier(best), len(by_suit[s]), -dump_value(best))

    # Prefer suits that are not obviously long when dumping faces/mids.
    ranked = sorted(by_suit.keys(), key=suit_score)
    for suit in ranked:
        best = best_in_suit(suit)
        if dump_tier(best) >= 2 and len(by_suit[suit]) >= LONG_SUIT_LEN:
            continue
        if dump_tier(best) >= 1:
            return raise_equivalence(best, hand, hand, accounted=set(hand))

    suit = min(by_suit, key=lambda s: (len(by_suit[s]), min(by_suit[s])))
    non_keepers = [c for c in by_suit[suit] if not is_keeper(c)]
    choice = min(non_keepers) if non_keepers else min(by_suit[suit])
    return raise_equivalence(choice, hand, hand, accounted=set(hand))


def _survival_respond(hand, lead_card, highest):
    """Follow/thulla heuristic: cash faces on follow without length gate."""
    same = [c for c in hand if c.colour == lead_card.colour]
    if same:
        winners = [c for c in same if highest is None or c > highest]
        under = [c for c in same if highest is not None and c < highest]
        face_winners = [c for c in winners if is_face(c)]
        # Rollouts have no void view — cash face winners; otherwise best dump.
        if face_winners:
            choice = max(face_winners, key=lambda c: (dump_value(c), c))
        elif winners and not under:
            choice = max(winners, key=lambda c: (dump_tier(c), dump_value(c), c))
        elif under:
            choice = max(under, key=lambda c: (dump_tier(c), dump_value(c), c))
        elif winners:
            choice = min(winners)
        else:
            choice = max(same, key=lambda c: (dump_tier(c), dump_value(c), c))
        return raise_equivalence(choice, hand, same, accounted=set(hand))
    faces = [c for c in hand if is_face(c)]
    if faces:
        choice = max(faces, key=lambda c: (dump_value(c), c))
    else:
        non_keepers = [c for c in hand if not is_keeper(c)]
        pool = non_keepers if non_keepers else hand
        choice = max(pool, key=lambda c: (dump_tier(c), dump_value(c), c))
    return raise_equivalence(choice, hand, hand, accounted=set(hand))


def _respond(hand, lead):
    """Legacy duck-follow used by take sims."""
    same = [c for c in hand if c.colour == lead.colour]
    if same:
        under = [c for c in same if c < lead]
        choice = max(under) if under else min(same)
        return raise_equivalence(choice, hand, same, accounted=set(hand))
    return raise_equivalence(max(hand), hand, hand, accounted=set(hand))


def _n_player_i_lose(hands, me_idx, leader_idx, max_tricks=200, use_survival=True):
    """Full-game sim. True iff me_idx is the sole leftover (last)."""
    hands = [list(h) for h in hands]
    n = len(hands)
    leader = leader_idx
    for _ in range(max_tricks):
        active = [i for i in range(n) if hands[i]]
        if len(active) <= 1:
            return bool(active) and active[0] == me_idx
        if leader not in active:
            leader = active[0]
        order = []
        start = active.index(leader)
        for k in range(len(active)):
            order.append(active[(start + k) % len(active)])
        stack = []
        colour = None
        highest = None
        highest_p = leader
        thulla = False
        for j, p in enumerate(order):
            if j == 0:
                if use_survival:
                    card = _survival_lead_card(hands[p])
                else:
                    card = min(hands[p])
                colour = card.colour
                highest = card
                highest_p = p
            else:
                if use_survival:
                    card = _survival_respond(hands[p], stack[0], highest)
                else:
                    card = _respond(hands[p], stack[0])
            hands[p].remove(card)
            stack.append(card)
            if card.colour != colour:
                hands[highest_p].extend(stack)
                leader = highest_p
                thulla = True
                break
            if card > highest:
                highest = card
                highest_p = p
        if not thulla:
            leader = highest_p
    survivors = [i for i in range(n) if hands[i]]
    return len(survivors) == 1 and survivors[0] == me_idx


def estimate_lead_lose_rates(view, my_hand, candidate_cards, samples=24):
    """For each lead card, estimate P(finish last) via deal sampling + survival playouts.

    Returns dict card -> lose_rate.
    """
    if not candidate_cards:
        return {}
    active = list(view.active_indices)
    me = view.me
    others = [p for p in active if p != me]
    rates = {c: 0.0 for c in candidate_cards}
    hits = {c: 0 for c in candidate_cards}
    n = 0
    for dealt in _sample_deals(view, my_hand, samples):
        n += 1
        full = [[] for _ in range(view.player_cnt)]
        full[me] = list(my_hand)
        for p in others:
            known = list(view.visible_cards(p, my_hand))
            sampled = list(dealt.get(p, []))
            full[p] = _pad_hand(known + sampled, view.hand_size(p))
        for card in candidate_cards:
            if card not in full[me]:
                continue
            hands = [list(h) for h in full]
            hands[me].remove(card)
            if _lead_card_then_lose(hands, me, card, active):
                hits[card] += 1
    if n == 0:
        return {c: 1.0 for c in candidate_cards}
    for c in candidate_cards:
        rates[c] = hits[c] / n
    return rates


def _lead_card_then_lose(hands, me_idx, lead_card, active_seats):
    """Play one trick with me leading lead_card, then survival playout. Return if me last."""
    n = len(hands)
    active_set = set(active_seats)
    order = []
    for k in range(1, n + 1):
        j = (me_idx + k) % n
        if j in active_set and hands[j]:
            order.append(j)
    stack = [lead_card]
    colour = lead_card.colour
    highest = lead_card
    highest_p = me_idx
    thulla = False
    for p in order:
        card = _survival_respond(hands[p], lead_card, highest)
        hands[p].remove(card)
        stack.append(card)
        if card.colour != colour:
            hands[highest_p].extend(stack)
            thulla = True
            leader = highest_p
            break
        if card > highest:
            highest = card
            highest_p = p
    if not thulla:
        leader = highest_p
    return _n_player_i_lose(hands, me_idx, leader, use_survival=True)
