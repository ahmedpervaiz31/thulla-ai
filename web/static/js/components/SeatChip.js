import { ordinal } from "../lib/ordinal.js";

/**
 * Opponent / AI seat chip for the arena ring.
 * @param {number} seatIdx
 * @param {object} seat
 * @param {number|null} whoseTurn
 * @returns {HTMLDivElement}
 */
export function createSeatChip(seatIdx, seat, whoseTurn) {
  const wrap = document.createElement("div");
  wrap.className = "seat-card";
  if (whoseTurn === seatIdx) wrap.classList.add("turn");
  if (!seat.active) wrap.classList.add("out");

  const name = document.createElement("div");
  name.className = "seat-name";
  name.textContent = seat.name;
  wrap.appendChild(name);

  const meta = document.createElement("div");
  meta.className = "seat-meta";
  if (!seat.active) {
    meta.textContent = seat.place
      ? `OUT • ${seat.place}${ordinal(seat.place)}`
      : "OUT";
  } else {
    meta.textContent = `${seat.hand_size} CARDS`;
  }
  wrap.appendChild(meta);

  const tag = document.createElement("div");
  tag.className = "turn-tag";
  tag.textContent = "TURN";
  wrap.appendChild(tag);

  const backs = document.createElement("div");
  backs.className = "backs";
  if (seat.active && !seat.is_human) {
    const show = seat.hand_size > 0 ? Math.min(3, seat.hand_size) : 0;
    for (let i = 0; i < show; i++) {
      const b = document.createElement("div");
      b.className = "card-back stacked";
      backs.appendChild(b);
    }
  }
  wrap.appendChild(backs);
  return wrap;
}

/**
 * Fill a side slot with one or more seat chips.
 * Left column: clockwise near-human is first in list → show at BOTTOM (reverse).
 */
export function fillSeatSlot(slotEl, seatOrList, side, seats, whoseTurn) {
  slotEl.innerHTML = "";
  slotEl.classList.remove("stack-col", "stack-row", "stack-many");
  if (seatOrList == null) return;

  const indices = Array.isArray(seatOrList) ? seatOrList.slice() : [seatOrList];
  if (side === "left" && indices.length > 1) indices.reverse();

  const stack = document.createElement("div");
  stack.className =
    side === "top" || side === "bottom" ? "seat-stack row" : "seat-stack col";
  if (indices.length >= 2) stack.classList.add("many");
  if (indices.length >= 3) stack.classList.add("crowded");

  indices.forEach((idx) => {
    const seat = seats[idx];
    if (seat) stack.appendChild(createSeatChip(idx, seat, whoseTurn));
  });
  slotEl.appendChild(stack);
}
