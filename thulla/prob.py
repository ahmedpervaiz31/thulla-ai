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
LEAD_PICKUP_WEIGHT = 0.2
LEAD_LIABILITY_WEIGHT = 0.1
LEAD_TIER_WEIGHT = 0.08
LEAD_SUIT_VOID_WEIGHT = 0.3
LEAD_VOID_COUNT_WEIGHT = 0.15
LOOKAHEAD_SAMPLES = 48
THULLA_ESCAPE_WEIGHT = 0.2
THULLA_SHED_WEIGHT = 0.15
THULLA_ESCAPE_HORIZON = 3
THULLA_SCORE_EPSILON = 0.02
# Full-game lose rollouts are expensive; only when the unknown pool is small.
THULLA_FULL_LOSE_MAX_UNKNOWN = 20
THULLA_LOSE_MAX_TRICKS = 48
THULLA_MC_MAX_CANDIDATES = 4


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


def _trick1_play_card(hand, lead_card, highest, player_idx, view=None):
    """Play one card on trick 1; force thulla when player is a known void in led suit."""
    suit = lead_card.colour
    same = [c for c in hand if c.colour == suit]
    if view is not None and view.is_void(player_idx, suit):
        same = []
    if same:
        winners = [c for c in same if highest is None or c > highest]
        under = [c for c in same if highest is not None and c < highest]
        face_winners = [c for c in winners if is_face(c)]
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


def _trick1_order(me_idx, active_seats, hands):
    n = len(hands)
    active_set = set(active_seats)
    order = []
    for k in range(1, n + 1):
        j = (me_idx + k) % n
        if j in active_set and hands[j]:
            order.append(j)
    return order


def _trick1_self_pickup(hands, me_idx, lead_card, active_seats, view=None):
    """True iff leader picks up the pot on trick 1 via thulla."""
    order = _trick1_order(me_idx, active_seats, hands)
    stack = [lead_card]
    colour = lead_card.colour
    highest = lead_card
    highest_p = me_idx
    thulla = False
    for p in order:
        card = _trick1_play_card(hands[p], lead_card, highest, p, view=view)
        hands[p].remove(card)
        stack.append(card)
        if card.colour != colour:
            hands[highest_p].extend(stack)
            thulla = True
            break
        if card > highest:
            highest = card
            highest_p = p
    return thulla and highest_p == me_idx


def immediate_self_thulla_prob(view, my_hand, lead_card, seats_after=None, samples=LOOKAHEAD_SAMPLES):
    """P(leader picks up the pot on trick 1 via thulla after leading lead_card)."""
    seats = list(
        seats_after
        if seats_after is not None
        else view.players_after_me_this_trick()
    )
    if not seats:
        return 0.0

    suit = lead_card.colour
    if view.is_void(seats[0], suit):
        return 1.0

    me = view.me
    active = list(view.active_indices)
    others = [p for p in active if p != me]
    hits = 0
    n = 0
    for dealt in _sample_deals(view, my_hand, samples):
        n += 1
        full = [[] for _ in range(view.player_cnt)]
        full[me] = list(my_hand)
        for p in others:
            known = list(view.visible_cards(p, my_hand))
            sampled = list(dealt.get(p, []))
            full[p] = _pad_hand(known + sampled, view.hand_size(p))
        if lead_card not in full[me]:
            continue
        hands = [list(h) for h in full]
        hands[me].remove(lead_card)
        if _trick1_self_pickup(hands, me, lead_card, active, view=view):
            hits += 1
    return hits / max(1, n)


def _lead_suit_risk(view, hand, suit, seats_after, samples=200):
    """P(thulla) and count of known voids after leader in `suit`."""
    seats = list(seats_after or view.players_after_me_this_trick())
    void_count = sum(1 for p in seats if view.is_void(p, suit))
    if void_count:
        return 1.0, void_count
    p = estimate_thulla_prob(view, suit, hand, seats_after=seats, samples=samples)
    return p, void_count


def score_lead_candidates(
    view,
    my_hand,
    candidate_cards,
    samples=LOOKAHEAD_SAMPLES,
    pickup_weight=LEAD_PICKUP_WEIGHT,
):
    """Composite lead scores: MC lose-rate + immediate self-thulla pickup penalty.

    Returns (scores, lose_rates, pickup_probs) dicts keyed by card.
    """
    if not candidate_cards:
        return {}, {}, {}
    seats = view.players_after_me_this_trick()
    if not seats:
        seats = [p for p in view.active_indices if p != view.me]
    lose_rates = estimate_lead_lose_rates(
        view, my_hand, candidate_cards, samples=samples
    )
    pickup_probs = {}
    scores = {}
    suit_risk_cache = {}
    # Pickup MC is secondary to lose-rate; keep it cheaper than the main loop.
    pickup_samples = max(8, min(samples, 12))
    for card in candidate_cards:
        suit = card.colour
        if suit not in suit_risk_cache:
            suit_risk_cache[suit] = _lead_suit_risk(
                view, my_hand, suit, seats, samples=min(samples, 80)
            )
        suit_p, void_count = suit_risk_cache[suit]
        p_pickup = immediate_self_thulla_prob(
            view, my_hand, card, seats_after=seats, samples=pickup_samples
        )
        pickup_probs[card] = p_pickup
        face_penalty = 0.0
        if dump_value(card) > 0:
            face_penalty = p_pickup * dump_value(card) / 10.0
        dump_safe = max(0.0, 1.0 - p_pickup)
        scores[card] = (
            lose_rates.get(card, 1.0)
            + pickup_weight * p_pickup
            + pickup_weight * face_penalty
            + LEAD_SUIT_VOID_WEIGHT * suit_p
            + LEAD_VOID_COUNT_WEIGHT * void_count
            - dump_value(card) * LEAD_LIABILITY_WEIGHT * dump_safe
            - dump_tier(card) * LEAD_TIER_WEIGHT * dump_safe
        )
    return scores, lose_rates, pickup_probs


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
            if _lead_card_then_lose(hands, me, card, active, view=view):
                hits[card] += 1
    if n == 0:
        return {c: 1.0 for c in candidate_cards}
    for c in candidate_cards:
        rates[c] = hits[c] / n
    return rates


def _lead_card_then_lose(hands, me_idx, lead_card, active_seats, view=None):
    """Play one trick with me leading lead_card, then survival playout. Return if me last."""
    order = _trick1_order(me_idx, active_seats, hands)
    stack = [lead_card]
    colour = lead_card.colour
    highest = lead_card
    highest_p = me_idx
    thulla = False
    for p in order:
        card = _trick1_play_card(hands[p], lead_card, highest, p, view=view)
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


def _resolve_thulla_dump(hands, me_idx, dump_card, view):
    """Apply mid-trick thulla dump: pot (trick + dump) goes to current highest; they lead.

    Real rules end the trick on the first off-suit play — seats after the dumper do not act.
    Returns (victim_idx, leader_idx).
    """
    victim = view.current_highest_player
    if victim is None:
        raise ValueError("thulla dump requires a current highest player")
    if dump_card not in hands[me_idx]:
        raise ValueError("dump card missing from hand")
    hands[me_idx].remove(dump_card)
    stack = list(view._info.trick_cards) + [dump_card]
    hands[victim].extend(stack)
    return victim, victim


def _survival_trick_once(hands, leader_idx):
    """Play one survival-policy trick.

    Returns (next_leader, discarded_set_or_None, thulla).
    discarded_set is the clean-trick stack when not thulla; else None.
    """
    active = [i for i in range(len(hands)) if hands[i]]
    if len(active) <= 1:
        return leader_idx, None, False
    if leader_idx not in active:
        leader_idx = active[0]
    order = []
    start = active.index(leader_idx)
    for k in range(len(active)):
        order.append(active[(start + k) % len(active)])
    stack = []
    colour = None
    highest = None
    highest_p = leader_idx
    for j, p in enumerate(order):
        if j == 0:
            card = _survival_lead_card(hands[p])
            colour = card.colour
            highest = card
            highest_p = p
        else:
            card = _survival_respond(hands[p], stack[0], highest)
        hands[p].remove(card)
        stack.append(card)
        if card.colour != colour:
            hands[highest_p].extend(stack)
            return highest_p, None, True
        if card > highest:
            highest = card
            highest_p = p
    return highest_p, set(stack), False


def _thulla_dump_then_outcomes(
    hands,
    me_idx,
    dump_card,
    view,
    horizon=THULLA_ESCAPE_HORIZON,
    max_tricks=THULLA_LOSE_MAX_TRICKS,
    full_lose=True,
):
    """After dumping dump_card: (i_lose, victim_away_soon, card_shed_soon).

    When full_lose is False, skip remaining-game survival (i_lose stays False)
    and only measure short-horizon away/shed — much cheaper early/mid game.
    """
    victim, leader = _resolve_thulla_dump(hands, me_idx, dump_card, view)
    victim_away_soon = not bool(hands[victim])
    card_shed_soon = False
    track = dump_card

    for _ in range(horizon):
        active = [i for i in range(len(hands)) if hands[i]]
        if len(active) <= 1:
            break
        if not hands[victim]:
            victim_away_soon = True
            break
        leader, discarded, _thulla = _survival_trick_once(hands, leader)
        if discarded is not None and track in discarded:
            card_shed_soon = True
        if not hands[victim]:
            victim_away_soon = True

    if not full_lose:
        return False, victim_away_soon, card_shed_soon

    survivors = [i for i in range(len(hands)) if hands[i]]
    if len(survivors) <= 1:
        i_lose = len(survivors) == 1 and survivors[0] == me_idx
    else:
        i_lose = _n_player_i_lose(
            hands, me_idx, leader, max_tricks=max_tricks, use_survival=True
        )
    return i_lose, victim_away_soon, card_shed_soon


def estimate_thulla_dump_outcomes(
    view,
    my_hand,
    candidate_cards,
    samples=LOOKAHEAD_SAMPLES,
    horizon=THULLA_ESCAPE_HORIZON,
    full_lose=True,
):
    """Per dump card: lose_rate, p_victim_away_soon, p_card_shed_soon."""
    if not candidate_cards:
        return {}, {}, {}
    active = list(view.active_indices)
    me = view.me
    others = [p for p in active if p != me]
    lose_hits = {c: 0 for c in candidate_cards}
    away_hits = {c: 0 for c in candidate_cards}
    shed_hits = {c: 0 for c in candidate_cards}
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
            i_lose, away, shed = _thulla_dump_then_outcomes(
                hands, me, card, view, horizon=horizon, full_lose=full_lose
            )
            if i_lose:
                lose_hits[card] += 1
            if away:
                away_hits[card] += 1
            if shed:
                shed_hits[card] += 1
    if n == 0:
        return (
            {c: 1.0 for c in candidate_cards},
            {c: 0.0 for c in candidate_cards},
            {c: 0.0 for c in candidate_cards},
        )
    lose_rates = {c: lose_hits[c] / n for c in candidate_cards}
    p_away = {c: away_hits[c] / n for c in candidate_cards}
    p_shed = {c: shed_hits[c] / n for c in candidate_cards}
    return lose_rates, p_away, p_shed


def shortlist_thulla_candidates(view, my_hand, candidates, max_n=THULLA_MC_MAX_CANDIDATES):
    """Keep dump MC cheap: diversify suits, prefer void-punish and liability extremes."""
    opts = list(candidates)
    if len(opts) <= max_n:
        return opts
    victim = view.current_highest_player
    counts = {}
    for c in my_hand:
        counts[c.colour] = counts.get(c.colour, 0) + 1

    def rank_key(card):
        void_hit = (
            0
            if victim is not None and view.is_void(victim, card.colour)
            else 1
        )
        creates_void = 0 if counts.get(card.colour, 0) == 1 else 1
        extreme = -abs(dump_value(card))
        return (void_hit, creates_void, extreme, -dump_tier(card), card.code())

    ranked = sorted(opts, key=rank_key)
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


def score_thulla_candidates(
    view,
    my_hand,
    candidate_cards,
    samples=LOOKAHEAD_SAMPLES,
    escape_weight=THULLA_ESCAPE_WEIGHT,
    shed_weight=THULLA_SHED_WEIGHT,
    horizon=THULLA_ESCAPE_HORIZON,
    full_lose=None,
):
    """Composite thulla-dump scores (lower better).

    score = lose_rate
          + escape_weight * p_victim_away_soon
          + shed_weight * p_card_shed_soon

    When full_lose is None, enable full-game lose rollouts only if
    free unknowns ≤ THULLA_FULL_LOSE_MAX_UNKNOWN.
    """
    if not candidate_cards:
        return {}, {}, {}
    if full_lose is None:
        full_lose = count_free_unknown(view, my_hand) <= THULLA_FULL_LOSE_MAX_UNKNOWN
    lose_rates, p_away, p_shed = estimate_thulla_dump_outcomes(
        view,
        my_hand,
        candidate_cards,
        samples=samples,
        horizon=horizon,
        full_lose=full_lose,
    )
    scores = {}
    extras = {}
    counts = {}
    for c in my_hand:
        counts[c.colour] = counts.get(c.colour, 0) + 1
    victim = view.current_highest_player
    for card in candidate_cards:
        lr = lose_rates.get(card, 1.0) if full_lose else 0.0
        away = p_away.get(card, 0.0)
        shed = p_shed.get(card, 0.0)
        scores[card] = lr + escape_weight * away + shed_weight * shed
        extras[card] = {
            "lose_rate": lr,
            "p_victim_away_soon": away,
            "p_card_shed_soon": shed,
            "creates_void": counts.get(card.colour, 0) == 1,
            "victim_void_suit": bool(
                victim is not None and view.is_void(victim, card.colour)
            ),
            "full_lose": full_lose,
        }
    return scores, lose_rates, extras


def thulla_dump_score_key(card, scores, extras=None):
    """Lower is better. Ties: my void, low shed, victim void suit, then dump_value."""
    extras = extras or {}
    info = extras.get(card) or {}
    return (
        scores.get(card, 1.0),
        0 if info.get("creates_void") else 1,
        info.get("p_card_shed_soon", 0.0),
        0 if info.get("victim_void_suit") else 1,
        -dump_value(card),
        card.code(),
    )
