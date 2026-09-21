"""Minimal seat-relative observation / action encoding for Thulla DMC."""

from __future__ import annotations

from typing import Union

import numpy as np

from thulla.cards import COLOUR_CARDS, NUMBER_CARDS, Card, create_deck

NUM_PLAYERS = 4
CARD_DIM = 52
# Card one-hot (52) + ASK + PASS
TAKE_ASK_IDX = 52
TAKE_PASS_IDX = 53
ACTION_DIM = 54
HISTORY_LEN = 20
MAX_HAND = 14  # one-hot sizes 0..13

ASK = "ASK"
PASS = "PASS"
Action = Union[Card, str]

# my_hand + free_unknowns + trick + known_others(3*52)
# + led_suit(4) + high + first_trick
# + hand_sizes(4*14) + voids_others(3*4) + is_take_phase + i_am_leader
#
# free_unknowns = cards not yet assigned (not my hand / discarded / trick / known).
# Discarded is implied: deck − my − free − known − trick.
# known_others uses visible_cards (thulla/take holdings; full hand in heads-up).
X_NO_ACTION_DIM = (
    52  # my_hand
    + 52  # free unknowns still available to assign
    + 52  # current trick
    + (3 * 52)  # known/visible holdings for other seats (clockwise)
    + 4  # led suit
    + 52  # current high
    + 1  # first trick
    + (NUM_PLAYERS * MAX_HAND)  # hand sizes
    + (3 * 4)  # voids for others
    + 1  # take phase
    + 1  # i_am_leader
)
X_DIM = X_NO_ACTION_DIM + ACTION_DIM
Z_ROWS = HISTORY_LEN
Z_DIM = CARD_DIM

_FULL_DECK = tuple(create_deck())
_CARD_TO_IDX = {
    c: COLOUR_CARDS.index(c.colour) * 13 + NUMBER_CARDS.index(c.number) for c in _FULL_DECK
}


def card_index(card: Card) -> int:
    return _CARD_TO_IDX[card]


def cards_to_array(cards) -> np.ndarray:
    arr = np.zeros(CARD_DIM, dtype=np.float32)
    for c in cards:
        arr[card_index(c)] = 1.0
    return arr


def one_hot_size(n: int, max_n: int = MAX_HAND) -> np.ndarray:
    arr = np.zeros(max_n, dtype=np.float32)
    n = max(0, min(int(n), max_n - 1))
    arr[n] = 1.0
    return arr


def relative_seats(me: int, n: int = NUM_PLAYERS) -> list[int]:
    """Seat order starting at me, clockwise."""
    return [(me + i) % n for i in range(n)]


def encode_action(action: Action) -> np.ndarray:
    """Encode a card play or ASK/PASS take decision into ACTION_DIM."""
    arr = np.zeros(ACTION_DIM, dtype=np.float32)
    if isinstance(action, Card):
        arr[card_index(action)] = 1.0
    elif action == ASK:
        arr[TAKE_ASK_IDX] = 1.0
    elif action == PASS:
        arr[TAKE_PASS_IDX] = 1.0
    else:
        raise ValueError(f"unknown action {action!r}")
    return arr


def encode_history(play_history: list[Card]) -> np.ndarray:
    """Last HISTORY_LEN plays as (HISTORY_LEN, 52), padded with zeros at the front."""
    z = np.zeros((HISTORY_LEN, CARD_DIM), dtype=np.float32)
    recent = play_history[-HISTORY_LEN:]
    offset = HISTORY_LEN - len(recent)
    for i, card in enumerate(recent):
        z[offset + i] = cards_to_array([card])
    return z


def encode_state(
    game,
    seat: int,
    trick,
    play_history: list[Card],
    *,
    take_phase: bool = False,
    i_am_leader: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Return (x_no_action, z) for `seat` under imperfect info.

    Hard facts only: my hand, free unknown pool, trick, known/visible holdings
    (thulla pickup / take; full opponent hand when heads-up deduction applies),
    voids, hand sizes. Soft duck / suit-high hints are omitted.
    """
    player = game.players[seat]
    my_cards = list(player.hand)
    if trick is not None:
        view = game.view_for_seat(trick, seat)
    else:
        remaining = [p for p in game.active_in_order(seat) if p != seat]
        view = game.info.view_for(seat, remaining)

    my_hand = cards_to_array(my_cards)
    # Unassigned pool — discarded is recoverable as deck − my − free − known − trick.
    # Heads-up: free_cards() is empty once the opponent hand is fully deduced.
    free = cards_to_array(view.free_cards(my_cards))
    trick_cards = cards_to_array(getattr(game.info, "trick_cards", []) or [])

    known_others = []
    sizes = []
    voids = []
    for rel in relative_seats(seat):
        sizes.append(one_hot_size(view.hand_size(rel)))
        if rel == seat:
            continue
        # visible_cards = hard known holdings, or full deduced hand in heads-up.
        known_others.append(cards_to_array(view.visible_cards(rel, my_cards)))
        v = np.zeros(4, dtype=np.float32)
        for si, suit in enumerate(COLOUR_CARDS):
            if view.is_void(rel, suit):
                v[si] = 1.0
        voids.append(v)

    led = np.zeros(4, dtype=np.float32)
    if trick is not None and trick.colour is not None:
        led[COLOUR_CARDS.index(trick.colour)] = 1.0

    high = (
        cards_to_array([trick.highest_card])
        if trick is not None and trick.highest_card
        else np.zeros(CARD_DIM, dtype=np.float32)
    )
    first = np.array(
        [1.0 if (trick is not None and trick.first_trick) else 0.0], dtype=np.float32
    )
    phase = np.array(
        [1.0 if take_phase else 0.0, 1.0 if i_am_leader else 0.0], dtype=np.float32
    )

    x = np.concatenate(
        [
            my_hand,
            free,
            trick_cards,
            *known_others,
            led,
            high,
            first,
            *sizes,
            *voids,
            phase,
        ]
    ).astype(np.float32)
    assert x.shape == (X_NO_ACTION_DIM,), x.shape
    z = encode_history(play_history)
    return x, z


def build_action_batch(x_no_action: np.ndarray, z: np.ndarray, legal: list[Action]):
    """Batch (state, action) pairs for every legal action — DouZero-style scoring."""
    n = len(legal)
    x_batch = np.zeros((n, X_DIM), dtype=np.float32)
    z_batch = np.zeros((n, Z_ROWS, Z_DIM), dtype=np.float32)
    for i, action in enumerate(legal):
        x_batch[i, :X_NO_ACTION_DIM] = x_no_action
        x_batch[i, X_NO_ACTION_DIM:] = encode_action(action)
        z_batch[i] = z
    return x_batch, z_batch
