import { RANK_ORDER, RED_SUITS, SUIT_ORDER } from "../constants/suits.js";
import { SORT_RANK } from "../constants/lobby.js";

/**
 * @param {string} code
 * @returns {{ rank: string, suit: string, red: boolean }}
 */
export function parseCode(code) {
  const m = String(code)
    .toUpperCase()
    .match(/^(10|[2-9JQKA])([SHDC])$/);
  if (!m) return { rank: code, suit: "?", red: false };
  return { rank: m[1], suit: m[2], red: RED_SUITS.has(m[2]) };
}

/**
 * @param {string[]} codes
 * @param {"suit"|"rank"} sortMode
 */
export function sortHand(codes, sortMode) {
  return [...codes].sort((a, b) => {
    const pa = parseCode(a);
    const pb = parseCode(b);
    if (sortMode === SORT_RANK) {
      return (
        RANK_ORDER[pa.rank] - RANK_ORDER[pb.rank] ||
        SUIT_ORDER[pa.suit] - SUIT_ORDER[pb.suit]
      );
    }
    return (
      SUIT_ORDER[pa.suit] - SUIT_ORDER[pb.suit] ||
      RANK_ORDER[pa.rank] - RANK_ORDER[pb.rank]
    );
  });
}
