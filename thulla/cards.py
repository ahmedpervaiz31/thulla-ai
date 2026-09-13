NUMBER_CARDS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
COLOUR_CARDS = ["Diamond", "Heart", "Spade", "Club"]
SUIT_LETTER = {"Diamond": "D", "Heart": "H", "Spade": "S", "Club": "C"}

_COLOUR_ALIASES = {}
for _name in COLOUR_CARDS:
    _COLOUR_ALIASES[_name.upper()] = _name
    _COLOUR_ALIASES[_name.upper() + "S"] = _name
    _COLOUR_ALIASES[_name[0].upper()] = _name


class Card:
    def __init__(self, number, colour):
        self.number = number
        self.colour = colour

    def code(self):
        return f"{self.number}{SUIT_LETTER[self.colour]}"

    def __str__(self):
        return self.code()

    def __repr__(self):
        return self.code()

    def __eq__(self, other):
        return isinstance(other, Card) and self.number == other.number and self.colour == other.colour

    def __lt__(self, other):
        return isinstance(other, Card) and NUMBER_CARDS.index(self.number) < NUMBER_CARDS.index(other.number)

    def __hash__(self):
        return hash((self.number, self.colour))


def parse_card(text):
    """Parse compact forms like AH, 10S, Q hearts. Returns None if unrecognized."""
    if text is None:
        return None
    compact = str(text).strip().upper().replace(" ", "").replace("-", "")
    if not compact:
        return None
    ranks = sorted(NUMBER_CARDS, key=len, reverse=True)
    for rank in ranks:
        if compact.startswith(rank.upper()):
            colour = _COLOUR_ALIASES.get(compact[len(rank):])
            if colour:
                return Card(rank, colour)
            return None
    return None


def cards_of_suit(colour):
    return [Card(num, colour) for num in NUMBER_CARDS]


def raise_equivalence(card, hand, legal_moves, accounted=None):
    """
    Prefer the highest card in `card`'s equivalence class among legal moves.

    Two same-suit holdings are equivalent when every rank between them is already
    accounted for (held by us, discarded, in the trick, or known). Playing the
    low end of such a block is a thulla blunder: an opponent who picks it up can
    undercut the rest of the block.
    """
    if card is None:
        return card
    legal_set = set(legal_moves)
    group = equivalence_class(card, hand, accounted=accounted)
    raised = [c for c in group if c in legal_set]
    return max(raised) if raised else card


def equivalence_class(card, hand, accounted=None):
    """Connected same-suit block containing `card` (see raise_equivalence)."""
    suit = card.colour
    held = sorted({c for c in hand if c.colour == suit} | {card})
    accounted = set(accounted or []) | set(hand)
    suit_all = cards_of_suit(suit)

    groups = []
    for c in held:
        if not groups:
            groups.append([c])
            continue
        prev = groups[-1][-1]
        live_between = any(prev < mid < c and mid not in accounted for mid in suit_all)
        if live_between:
            groups.append([c])
        else:
            groups[-1].append(c)

    for group in groups:
        if card in group:
            return list(group)
    return [card]


def valid_moves(hand, expected_cards):
    if not expected_cards:
        return list(hand)
    common = [card for card in hand if card in expected_cards]
    return common if common else list(hand)


def format_cards(cards):
    return " ".join(card.code() for card in cards)


def format_hand(cards):
    """One line per suit, e.g. Heart  2 6 7 9"""
    by_suit = {colour: [] for colour in COLOUR_CARDS}
    for card in cards:
        by_suit[card.colour].append(card.number)
    lines = []
    for colour in COLOUR_CARDS:
        ranks = by_suit[colour]
        if ranks:
            lines.append(f"  {colour:<8} {' '.join(ranks)}")
    return "\n".join(lines) if lines else "  (empty)"


def create_deck():
    return [Card(number=number, colour=colour) for colour in COLOUR_CARDS for number in NUMBER_CARDS]
