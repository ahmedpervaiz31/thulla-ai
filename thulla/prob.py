import random


def estimate_thulla_prob(view, suit, my_hand, seats_after, samples=200):
    """P(someone in seats_after cannot follow suit)."""
    seats = list(seats_after)
    if not seats:
        return 0.0
    if any(view.is_void(p, suit) for p in seats):
        return 1.0

    max_copies = len(view.unseen_of(suit, my_hand))
    for p in seats:
        max_copies += sum(1 for c in view.known_cards(p) if c.colour == suit)
    if len(seats) > max_copies:
        return 1.0

    if all(any(c.colour == suit for c in view.known_cards(p)) for p in seats):
        if not any(c.colour == suit for c in view.free_cards(my_hand)):
            return 0.0

    hits = 0
    for dealt in _sample_deals(view, my_hand, samples):
        if _someone_void(dealt, view, seats, suit):
            hits += 1
    return hits / max(1, samples)


def _someone_void(dealt, view, seats, suit):
    for p in seats:
        if view.is_void(p, suit):
            return True
        has = any(c.colour == suit for c in view.known_cards(p))
        has = has or any(c.colour == suit for c in dealt.get(p, []))
        if not has:
            return True
    return False


def _sample_deals(view, my_hand, samples):
    others = [p for p in view.active_indices if p != view.me]
    slots = {p: view.unknown_slots(p) for p in others}
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
    my_suits = {c.colour for c in my_hand}
    if any(view.is_void(neighbor_idx, s) for s in my_suits):
        return True
    known = list(view.known_cards(neighbor_idx))
    if not known:
        return False
    my_voids = set()
    for s in ("Diamond", "Heart", "Spade", "Club"):
        if view.is_void(view.me, s) or not any(c.colour == s for c in my_hand):
            my_voids.add(s)
    hits = sum(1 for c in known if c.colour in my_voids)
    return hits * 2 >= len(known)


def compare_take_lose_rates(view, my_hand, neighbor_idx, other_idx, samples=40):
    """Return (lose_rate_keep, lose_rate_merge)."""
    neighbor_known = list(view.known_cards(neighbor_idx))
    other_known = list(view.known_cards(other_idx))
    lose_keep = 0
    lose_merge = 0
    n = 0
    for dealt in _sample_deals(view, my_hand, samples):
        n += 1
        neigh = _pad_hand(
            neighbor_known + list(dealt.get(neighbor_idx, [])),
            view.hand_size(neighbor_idx),
        )
        other = _pad_hand(
            other_known + list(dealt.get(other_idx, [])),
            view.hand_size(other_idx),
        )
        if _three_way_i_lose(list(my_hand), neigh, other):
            lose_keep += 1
        if _heads_up_i_lose(list(my_hand) + neigh, other):
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


def _liability_score(card):
    if card.number == "A":
        return 2
    if card.number == "K":
        return 1
    return 0


def _survival_lead_card(hand):
    """Lead heuristic for rollouts (no MC): dump A/K suit if any, else max of shortest."""
    by_suit = {}
    for c in hand:
        by_suit.setdefault(c.colour, []).append(c)
    with_liab = [
        s for s, cs in by_suit.items() if any(_liability_score(c) > 0 for c in cs)
    ]
    if with_liab:
        suit = max(
            with_liab,
            key=lambda s: max(_liability_score(c) for c in by_suit[s]),
        )
        return max(by_suit[suit], key=lambda c: (_liability_score(c), c))
    suit = min(by_suit, key=lambda s: (len(by_suit[s]), min(by_suit[s])))
    return max(by_suit[suit])


def _survival_respond(hand, lead_card, highest):
    """Follow/thulla heuristic matching soft_follow + liability dump."""
    same = [c for c in hand if c.colour == lead_card.colour]
    if same:
        if highest is not None and len(hand) > 2:
            under = [c for c in same if c < highest]
            if under:
                return max(under)
        return max(same)
    liab = [c for c in hand if _liability_score(c) > 0]
    if liab:
        return max(liab, key=lambda c: (_liability_score(c), c))
    return max(hand)


def _respond(hand, lead):
    """Legacy duck-follow used by take sims."""
    same = [c for c in hand if c.colour == lead.colour]
    if same:
        under = [c for c in same if c < lead]
        return max(under) if under else min(same)
    return max(hand)


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
            known = list(view.known_cards(p))
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
