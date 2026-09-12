import { SUIT_SYM } from "../constants/suits.js";
import { parseCode } from "../lib/cards.js";

/**
 * @param {string} code
 * @param {{
 *   small?: boolean,
 *   legal?: boolean,
 *   selected?: boolean,
 *   dim?: boolean,
 *   dealIn?: boolean,
 *   showTag?: boolean,
 *   onClick?: (ev: Event) => void,
 * }} [opts]
 * @returns {HTMLButtonElement}
 */
export function createCardEl(code, opts = {}) {
  const { rank, suit, red } = parseCode(code);
  const el = document.createElement("button");
  el.type = "button";
  el.className = [
    "playing-card",
    red ? "red" : "black",
    opts.small ? "small" : "",
    opts.legal ? "legal" : "",
    opts.selected ? "selected" : "",
    opts.dim ? "dim" : "",
    opts.dealIn ? "deal-in" : "",
  ]
    .filter(Boolean)
    .join(" ");
  el.dataset.code = code;

  const rankEl = document.createElement("span");
  rankEl.className = "rank";
  rankEl.textContent = rank;

  const suitEl = document.createElement("span");
  suitEl.className = "suit";
  suitEl.textContent = SUIT_SYM[suit] || "?";

  el.append(rankEl, suitEl);

  if (opts.legal && opts.showTag) {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = "LEGAL";
    el.appendChild(tag);
  }

  if (opts.onClick) el.addEventListener("click", opts.onClick);
  return el;
}
