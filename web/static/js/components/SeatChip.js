import { ordinal } from "../lib/ordinal.js";

/**
 * Opponent / AI seat chip for the arena ring.
 * @param {number} seatIdx
 * @param {object} seat
 * @param {number|null} whoseTurn
 * @param {{ turnLabel?: string }} [opts]
 * @returns {HTMLDivElement}
 */
export function createSeatChip(seatIdx, seat, whoseTurn, opts = {}) {
  const wrap = document.createElement("div");
  wrap.className = "seat-card";
  wrap.dataset.seat = String(seatIdx);
  applySeatChip(wrap, seatIdx, seat, whoseTurn, opts);
  return wrap;
}

/**
 * Update an existing chip in place (keeps CSS transitions alive).
 */
export function applySeatChip(wrap, seatIdx, seat, whoseTurn, opts = {}) {
  wrap.classList.toggle("turn", whoseTurn === seatIdx);
  wrap.classList.toggle("out", !seat.active);

  let name = wrap.querySelector(".seat-name");
  if (!name) {
    name = document.createElement("div");
    name.className = "seat-name";
    wrap.appendChild(name);
  }
  name.textContent = seat.name;

  let meta = wrap.querySelector(".seat-meta");
  if (!meta) {
    meta = document.createElement("div");
    meta.className = "seat-meta";
    wrap.appendChild(meta);
  }
  if (!seat.active) {
    meta.textContent = seat.place
      ? `OUT • ${seat.place}${ordinal(seat.place)}`
      : "OUT";
  } else {
    meta.textContent = `${seat.hand_size} CARDS`;
  }

  let tag = wrap.querySelector(".turn-tag");
  if (!tag) {
    tag = document.createElement("div");
    tag.className = "turn-tag";
    wrap.appendChild(tag);
  }
  tag.textContent = opts.turnLabel || "TURN";

  let backs = wrap.querySelector(".backs");
  if (!backs) {
    backs = document.createElement("div");
    backs.className = "backs";
    wrap.appendChild(backs);
  }
  const wantBacks =
    seat.active && !seat.is_human
      ? seat.hand_size > 0
        ? Math.min(3, seat.hand_size)
        : 0
      : 0;
  const haveBacks = backs.querySelectorAll(".card-back").length;
  if (haveBacks !== wantBacks) {
    backs.innerHTML = "";
    for (let i = 0; i < wantBacks; i++) {
      const b = document.createElement("div");
      b.className = "card-back stacked";
      backs.appendChild(b);
    }
  }
}

/**
 * Fill a side slot with one or more seat chips.
 * Left column: clockwise near-human is first in list → show at BOTTOM (reverse).
 * Reuses existing chips when the seat list is unchanged so turn glow can transition.
 */
export function fillSeatSlot(slotEl, seatOrList, side, seats, whoseTurn, opts = {}) {
  if (seatOrList == null) {
    slotEl.innerHTML = "";
    slotEl.classList.remove("stack-col", "stack-row", "stack-many");
    return;
  }

  const indices = Array.isArray(seatOrList) ? seatOrList.slice() : [seatOrList];
  if (side === "left" && indices.length > 1) indices.reverse();

  const sig = `${side}|${indices.join(",")}`;
  let stack = slotEl.querySelector(".seat-stack");
  const canReuse =
    stack &&
    slotEl.dataset.seatSig === sig &&
    stack.children.length === indices.length;

  if (!canReuse) {
    slotEl.innerHTML = "";
    slotEl.classList.remove("stack-col", "stack-row", "stack-many");
    stack = document.createElement("div");
    stack.className =
      side === "top" || side === "bottom" ? "seat-stack row" : "seat-stack col";
    if (indices.length >= 2) stack.classList.add("many");
    if (indices.length >= 3) stack.classList.add("crowded");
    indices.forEach((idx) => {
      const seat = seats[idx];
      if (seat) stack.appendChild(createSeatChip(idx, seat, whoseTurn, opts));
    });
    slotEl.appendChild(stack);
    slotEl.dataset.seatSig = sig;
    return;
  }

  indices.forEach((idx, i) => {
    const seat = seats[idx];
    const chip = stack.children[i];
    if (seat && chip) applySeatChip(chip, idx, seat, whoseTurn, opts);
  });
}
