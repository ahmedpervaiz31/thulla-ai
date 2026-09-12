/** Suit symbols, names, and sort orders for Thulla cards. */

export const SUIT_SYM = Object.freeze({
  S: "♠",
  H: "♥",
  D: "♦",
  C: "♣",
});

export const SUIT_NAME = Object.freeze({
  S: "SPADES",
  H: "HEARTS",
  D: "DIAMONDS",
  C: "CLUBS",
  Spade: "SPADES",
  Heart: "HEARTS",
  Diamond: "DIAMONDS",
  Club: "CLUBS",
});

/** Lead-suit string from API → single-letter code. */
export const LEAD_TO_CODE = Object.freeze({
  Spade: "S",
  Heart: "H",
  Diamond: "D",
  Club: "C",
});

export const RED_SUITS = new Set(["H", "D", "Heart", "Diamond"]);

/** Spades, Hearts, Clubs, Diamonds — black / red / black / red */
export const SUIT_ORDER = Object.freeze({ S: 0, H: 1, C: 2, D: 3 });

export const RANK_ORDER = Object.freeze({
  "2": 0,
  "3": 1,
  "4": 2,
  "5": 3,
  "6": 4,
  "7": 5,
  "8": 6,
  "9": 7,
  "10": 8,
  J: 9,
  Q: 10,
  K: 11,
  A: 12,
});
