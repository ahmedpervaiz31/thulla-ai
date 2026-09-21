import { LEAD_TO_CODE, RANK_ORDER, SUIT_NAME, SUIT_SYM } from "../constants/suits.js";
import { parseCode, sortHand } from "../lib/cards.js";
import { el } from "../lib/dom.js";
import { bindEdgePad, setPadOpen } from "../lib/edgePad.js";
import { ordinal } from "../lib/ordinal.js";

const SUIT_ORDER = ["Spade", "Heart", "Club", "Diamond"];
const RANKS_ASC = Object.freeze(
  Object.keys(RANK_ORDER).sort((a, b) => RANK_ORDER[a] - RANK_ORDER[b])
);

/**
 * Right-edge intel pad: discarded cards, known holdings, voids.
 * Open state shifts the table + controls left; pad itself never steals clicks
 * from the play surface (pointer-events only on handle + panel).
 */
export function bindScratchPad(root, { onToggle } = {}) {
  bindEdgePad(root, {
    handleRole: "scratch-toggle",
    openClass: "scratch-open",
    openSign: -1,
    onToggle,
  });
}

export function setScratchOpen(root, open) {
  setPadOpen(root, "scratch-open", "scratch-toggle", open, {
    openTitle: "Open scratch pad",
    closeTitle: "Close scratch pad",
  });
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
  if (info.complete_info) {
    body.appendChild(
      emptyNote("Heads-up: opponent hand is fully known from discards + your cards.")
    );
  }
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
    s: info.suit_high_shown,
    t: info.trick_cards,
    c: info.complete_info || false,
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

    const highShown = info.suit_high_shown?.[i] || {};
    const highKeys = Object.keys(highShown);
    if (highKeys.length) {
      const highBlock = el("div", "scratch-block");
      highBlock.appendChild(el("div", "scratch-label", "SUIT HIGH"));
      const tags = el("div", "scratch-voids");
      for (const suit of sortSuits(highKeys)) {
        const tag = el("span", "scratch-void");
        const code = LEAD_TO_CODE[suit];
        tag.textContent = `${SUIT_SYM[code] || ""} ≥ ${shortCode(highShown[suit])}`;
        if (suit === "Heart" || suit === "Diamond") tag.classList.add("red");
        tags.appendChild(tag);
      }
      highBlock.appendChild(tags);
      card.appendChild(highBlock);
    }

    const ceilingKeys = Object.keys(ceilings);
    const duckLines = [];
    for (const suit of sortSuits(ceilingKeys)) {
      const { played, ceiling } = ceilings[suit];
      const live = liveRanksBetween(played, ceiling, suit, info);
      if (!live.length) continue;
      duckLines.push({ suit, played, ceiling, live });
    }
    if (duckLines.length) {
      const ceilBlock = el("div", "scratch-block");
      ceilBlock.appendChild(el("div", "scratch-label", "DUCK HINT"));
      const list = el("div", "scratch-gaps");
      for (const row of duckLines) {
        const line = el("div", "scratch-gap");
        const code = LEAD_TO_CODE[row.suit];
        const liveTxt = row.live.map((c) => shortCode(c)).join(" ");
        line.textContent = `${SUIT_SYM[code] || ""} under ${shortCode(row.played)} vs ${shortCode(row.ceiling)} → maybe no ${liveTxt}`;
        list.appendChild(line);
      }
      ceilBlock.appendChild(list);
      card.appendChild(ceilBlock);
    }

    sec.appendChild(card);
  }
  return sec;
}

function liveRanksBetween(playedCode, ceilingCode, suitName, info) {
  const suit = LEAD_TO_CODE[suitName];
  if (!suit || !playedCode || !ceilingCode) return [];
  const lo = parseCode(playedCode);
  const hi = parseCode(ceilingCode);
  const accounted = new Set([
    ...(info.discarded || []),
    ...(info.trick_cards || []),
  ]);
  for (const cards of Object.values(info.known_holdings || {})) {
    for (const c of cards || []) accounted.add(c);
  }
  const live = [];
  for (const rank of RANKS_ASC) {
    if (RANK_ORDER[rank] <= RANK_ORDER[lo.rank]) continue;
    if (RANK_ORDER[rank] >= RANK_ORDER[hi.rank]) continue;
    const code = `${rank}${suit}`;
    if (!accounted.has(code)) live.push(code);
  }
  return live;
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
