import { LEAD_TO_CODE, SUIT_NAME, SUIT_SYM } from "../constants/suits.js";
import { parseCode, sortHand } from "../lib/cards.js";
import { ordinal } from "../lib/ordinal.js";

const SUIT_ORDER = ["Spade", "Heart", "Club", "Diamond"];

/**
 * Right-edge intel pad: discarded cards, known holdings, voids.
 * Open state shifts the table + controls left; pad itself never steals clicks
 * from the play surface (pointer-events only on handle + panel).
 */
export function bindScratchPad(root, { onToggle } = {}) {
  const handle = root.querySelector('[data-role="scratch-toggle"]');
  if (!handle) return;

  let dragStartX = null;
  let dragMoved = false;
  let dragStartOpen = false;

  handle.addEventListener("click", (ev) => {
    if (dragMoved) {
      ev.preventDefault();
      return;
    }
    const open = !root.classList.contains("scratch-open");
    onToggle?.(open);
  });

  const onPointerDown = (ev) => {
    if (ev.button != null && ev.button !== 0) return;
    dragStartX = ev.clientX;
    dragMoved = false;
    dragStartOpen = root.classList.contains("scratch-open");
    handle.setPointerCapture?.(ev.pointerId);
  };

  const onPointerMove = (ev) => {
    if (dragStartX == null) return;
    const dx = dragStartX - ev.clientX; // pull left = positive
    if (Math.abs(dx) > 10) dragMoved = true;
    if (!dragStartOpen && dx > 48) {
      dragStartOpen = true;
      onToggle?.(true);
    } else if (dragStartOpen && dx < -48) {
      dragStartOpen = false;
      onToggle?.(false);
    }
  };

  const onPointerUp = () => {
    dragStartX = null;
  };

  handle.addEventListener("pointerdown", onPointerDown);
  handle.addEventListener("pointermove", onPointerMove);
  handle.addEventListener("pointerup", onPointerUp);
  handle.addEventListener("pointercancel", onPointerUp);
}

export function setScratchOpen(root, open) {
  root.classList.toggle("scratch-open", open);
  const handle = root.querySelector('[data-role="scratch-toggle"]');
  if (handle) {
    handle.setAttribute("aria-expanded", open ? "true" : "false");
    handle.title = open ? "Close scratch pad" : "Open scratch pad";
  }
}

/**
 * Rebuild pad body from game.public_info. Skips if signature unchanged.
 */
export function renderScratchPad(root, game) {
  const body = root.querySelector('[data-role="scratch-body"]');
  if (!body || !game) return;

  const info = game.public_info;
  const sig = infoSignature(info, game.seats);
  if (body.dataset.sig === sig) return;
  body.dataset.sig = sig;

  body.innerHTML = "";
  if (!info) {
    body.appendChild(emptyNote("No public intel yet."));
    return;
  }

  body.appendChild(sectionDiscarded(info.discarded || []));
  body.appendChild(sectionSeats(game.seats || [], info));
}

function infoSignature(info, seats) {
  if (!info) return "none";
  return JSON.stringify({
    d: info.discarded,
    k: info.known_holdings,
    v: info.voids,
    h: (seats || []).map((s) => [s.seat, s.hand_size, s.active, s.place]),
    u: info.under_ceilings,
  });
}

function sectionDiscarded(codes) {
  const sec = el("section", "scratch-section");
  sec.appendChild(el("h3", "scratch-h", "DISCARDED"));
  if (!codes.length) {
    sec.appendChild(emptyNote("None yet — clean tricks land here."));
    return sec;
  }
  const bySuit = groupBySuit(codes);
  for (const suit of SUIT_ORDER) {
    const list = bySuit[suit] || [];
    if (!list.length) continue;
    const row = el("div", "scratch-suit-row");
    const label = el("span", "scratch-suit-label");
    label.innerHTML = `${SUIT_SYM[LEAD_TO_CODE[suit]] || ""} <span>${SUIT_NAME[suit] || suit}</span>`;
    label.classList.toggle("red", suit === "Heart" || suit === "Diamond");
    row.appendChild(label);
    const chips = el("div", "scratch-chips");
    for (const code of sortHand(list, "rank")) {
      chips.appendChild(chip(code));
    }
    row.appendChild(chips);
    sec.appendChild(row);
  }
  return sec;
}

function sectionSeats(seats, info) {
  const sec = el("section", "scratch-section");
  sec.appendChild(el("h3", "scratch-h", "SEATS"));

  for (const seat of seats) {
    const i = String(seat.seat);
    const known = info.known_holdings?.[i] || [];
    const voids = info.voids?.[i] || [];
    const ceilings = info.under_ceilings?.[i] || {};
    const card = el("article", "scratch-seat");
    if (!seat.active) card.classList.add("out");

    const head = el("div", "scratch-seat-head");
    const name = el("span", "scratch-seat-name", seat.name);
    const meta = el(
      "span",
      "scratch-seat-meta",
      seat.active
        ? `${seat.hand_size} CARD${seat.hand_size === 1 ? "" : "S"}`
        : seat.place
          ? `${seat.place}${ordinal(seat.place).toUpperCase()} OUT`
          : "OUT"
    );
    head.append(name, meta);
    card.appendChild(head);

    const knownBlock = el("div", "scratch-block");
    knownBlock.appendChild(el("div", "scratch-label", "KNOWN"));
    if (known.length) {
      const chips = el("div", "scratch-chips");
      for (const code of sortHand(known, "suit")) chips.appendChild(chip(code));
      knownBlock.appendChild(chips);
    } else {
      knownBlock.appendChild(el("div", "scratch-empty", "—"));
    }
    card.appendChild(knownBlock);

    const voidBlock = el("div", "scratch-block");
    voidBlock.appendChild(el("div", "scratch-label", "NO SUIT"));
    if (voids.length) {
      const tags = el("div", "scratch-voids");
      for (const suit of sortSuits(voids)) {
        const tag = el("span", "scratch-void");
        const code = LEAD_TO_CODE[suit];
        tag.textContent = `${SUIT_SYM[code] || ""} ${SUIT_NAME[suit] || suit}`;
        if (suit === "Heart" || suit === "Diamond") tag.classList.add("red");
        tags.appendChild(tag);
      }
      voidBlock.appendChild(tags);
    } else {
      voidBlock.appendChild(el("div", "scratch-empty", "—"));
    }
    card.appendChild(voidBlock);

    const ceilingKeys = Object.keys(ceilings);
    if (ceilingKeys.length) {
      const ceilBlock = el("div", "scratch-block");
      ceilBlock.appendChild(el("div", "scratch-label", "DUCK HINT"));
      const list = el("div", "scratch-gaps");
      for (const suit of sortSuits(ceilingKeys)) {
        const { played, ceiling } = ceilings[suit];
        const line = el("div", "scratch-gap");
        const code = LEAD_TO_CODE[suit];
        line.textContent = `${SUIT_SYM[code] || ""} likely empty ${shortCode(played)}…${shortCode(ceiling)}`;
        list.appendChild(line);
      }
      ceilBlock.appendChild(list);
      card.appendChild(ceilBlock);
    }

    sec.appendChild(card);
  }
  return sec;
}

function groupBySuit(codes) {
  const out = { Spade: [], Heart: [], Club: [], Diamond: [] };
  const nameByLetter = { S: "Spade", H: "Heart", C: "Club", D: "Diamond" };
  for (const code of codes) {
    const { suit } = parseCode(code);
    const name = nameByLetter[suit];
    if (name) out[name].push(code);
  }
  return out;
}

function sortSuits(suits) {
  return [...suits].sort(
    (a, b) => SUIT_ORDER.indexOf(a) - SUIT_ORDER.indexOf(b)
  );
}

function shortCode(code) {
  const { rank, suit } = parseCode(code);
  return `${rank}${SUIT_SYM[suit] || suit}`;
}

function chip(code) {
  const { rank, suit, red } = parseCode(code);
  const btn = el("span", `scratch-chip${red ? " red" : ""}`);
  btn.title = code;
  btn.innerHTML = `<b>${rank}</b><i>${SUIT_SYM[suit] || "?"}</i>`;
  return btn;
}

function emptyNote(text) {
  return el("p", "scratch-note", text);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
