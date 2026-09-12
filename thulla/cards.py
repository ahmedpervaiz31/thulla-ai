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
