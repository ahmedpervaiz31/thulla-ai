import { LEAD_TO_CODE, SUIT_NAME, SUIT_SYM } from "../constants/suits.js";
import { parseCode } from "../lib/cards.js";

const PANEL_MS = 220;

/**
 * Left-edge ideal-move coach (human mode). Mutual exclusion with scratch pad
 * is owned by TablePage via setIdealOpen / onToggle.
 */
export function bindIdealMove(root, { onToggle } = {}) {
  const handle = root.querySelector('[data-role="ideal-toggle"]');
  if (!handle) return;

  let dragStartX = null;
  let dragMoved = false;
  let dragStartOpen = false;

  handle.addEventListener("click", (ev) => {
    if (dragMoved) {
      ev.preventDefault();
      return;
    }
    const open = !root.classList.contains("ideal-open");
    onToggle?.(open);
  });

  const onPointerDown = (ev) => {
    if (ev.button != null && ev.button !== 0) return;
    dragStartX = ev.clientX;
    dragMoved = false;
    dragStartOpen = root.classList.contains("ideal-open");
    handle.setPointerCapture?.(ev.pointerId);
  };

  const onPointerMove = (ev) => {
    if (dragStartX == null) return;
    const dx = ev.clientX - dragStartX; // pull right = positive
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

export function setIdealOpen(root, open) {
  root.classList.toggle("ideal-open", open);
  const handle = root.querySelector('[data-role="ideal-toggle"]');
  if (handle) {
    handle.setAttribute("aria-expanded", open ? "true" : "false");
    handle.title = open ? "Close ideal move" : "Open ideal move";
  }
}

export function setIdealVisible(root, visible) {
  const pad = root.querySelector('[data-role="ideal-pad"]');
  if (pad) pad.classList.toggle("hidden", !visible);
  if (!visible) setIdealOpen(root, false);
}

export function panelTransitionMs() {
  return PANEL_MS;
}

/**
 * Render advice payload into the ideal panel body.
 */
export function renderIdealMove(root, advice, { loading = false } = {}) {
  const body = root.querySelector('[data-role="ideal-body"]');
  if (!body) return;

  body.innerHTML = "";

  if (loading) {
    body.appendChild(el("p", "ideal-note", "Running bot model…"));
    return;
  }

  if (!advice) {
    body.appendChild(el("p", "ideal-note", "Open to ask the bot what it would play."));
    return;
  }

  if (!advice.available) {
    body.appendChild(el("p", "ideal-note", advice.reason || "No advice right now."));
    return;
  }

  body.appendChild(renderRecommend(advice));
  body.appendChild(renderSituation(advice));

  if (advice.suit_risks?.length) {
    body.appendChild(renderRisks(advice.suit_risks));
  }
  if (advice.lookahead?.length) {
    body.appendChild(renderLookahead(advice.lookahead));
  }

  const stepsSec = el("section", "ideal-section");
  stepsSec.appendChild(el("h3", "ideal-h", "MODEL STEPS"));
  const list = el("ol", "ideal-steps");
  for (const step of advice.steps || []) {
    const li = el("li", "ideal-step");
    li.appendChild(el("div", "ideal-step-label", step.label || ""));
    li.appendChild(el("div", "ideal-step-detail", step.detail || ""));
    list.appendChild(li);
  }
  stepsSec.appendChild(list);
  body.appendChild(stepsSec);
}

function renderRecommend(advice) {
  const sec = el("section", "ideal-section");
  sec.appendChild(el("h3", "ideal-h", "RECOMMEND"));
  const box = el("div", "ideal-rec");
  const rec = advice.recommended || {};
  if (rec.type === "play" && rec.card) {
    box.appendChild(chip(rec.card));
    box.appendChild(
      el("span", "ideal-rec-text", `${kindLabel(advice.kind)} · ${rec.card}`)
    );
  } else if (rec.type === "take" || rec.type === "give") {
    box.appendChild(
      el(
        "span",
        "ideal-rec-text",
        rec.accept ? (rec.type === "take" ? "ASK / TAKE" : "GIVE") : "DECLINE"
      )
    );
  } else {
    box.appendChild(el("span", "ideal-rec-text", "—"));
  }
  sec.appendChild(box);
  return sec;
}

function renderSituation(advice) {
  const sec = el("section", "ideal-section");
  sec.appendChild(el("h3", "ideal-h", "SITUATION"));
  const sit = advice.situation || {};
  const lines = el("div", "ideal-lines");

  if (advice.kind === "lead" || advice.kind === "follow" || advice.kind === "thulla") {
    addLine(lines, "Kind", kindLabel(advice.kind));
    if (sit.lead_suit) {
      addLine(lines, "Lead", suitLabel(sit.lead_suit));
    }
    if (sit.current_highest) {
      addLine(lines, "High", sit.current_highest);
    }
    if (sit.legal_moves) {
      addLine(lines, "Legal", sit.legal_moves.join(" "));
    }
  } else if (advice.kind === "take") {
    addLine(lines, "Target", sit.target_name || "—");
    addLine(lines, "Cards", String(sit.n_cards ?? "—"));
    addLine(lines, "Leader", sit.i_am_leader ? "yes" : "no");
  } else if (advice.kind === "give") {
    addLine(lines, "Asker", sit.asker_name || "—");
    addLine(lines, "Cards", String(sit.n_cards ?? "—"));
  }

  sec.appendChild(lines);
  return sec;
}

function renderRisks(risks) {
  const sec = el("section", "ideal-section");
  sec.appendChild(el("h3", "ideal-h", "SUIT RISK"));
  const list = el("div", "ideal-risks");
  for (const r of risks) {
    const row = el("div", "ideal-risk");
    const pct = Math.round((r.p || 0) * 100);
    row.appendChild(el("span", "ideal-risk-suit", suitLabel(r.suit)));
    row.appendChild(el("span", "ideal-risk-p", `${pct}%`));
    row.appendChild(el("span", "ideal-risk-note", r.note || ""));
    list.appendChild(row);
  }
  sec.appendChild(list);
  return sec;
}

function renderLookahead(rows) {
  const sec = el("section", "ideal-section");
  sec.appendChild(el("h3", "ideal-h", "LOSE RATES"));
  const list = el("div", "ideal-risks");
  for (const r of rows) {
    const row = el("div", "ideal-risk");
    row.appendChild(chip(r.card));
    row.appendChild(
      el("span", "ideal-risk-p", `${Math.round((r.lose_rate || 0) * 100)}%`)
    );
    list.appendChild(row);
  }
  sec.appendChild(list);
  return sec;
}

function kindLabel(kind) {
  return (
    {
      lead: "LEAD",
      follow: "FOLLOW",
      thulla: "THULLA",
      take: "TAKE",
      give: "GIVE",
    }[kind] || (kind || "—").toUpperCase()
  );
}

function suitLabel(suit) {
  if (!suit) return "—";
  const code = LEAD_TO_CODE[suit] || suit;
  const sym = SUIT_SYM[code] || "";
  return `${sym} ${SUIT_NAME[suit] || suit}`.trim();
}

function addLine(parent, label, value) {
  const row = el("div", "ideal-line");
  row.appendChild(el("span", "ideal-line-k", label));
  row.appendChild(el("span", "ideal-line-v", value));
  parent.appendChild(row);
}

function chip(code) {
  const { rank, suit, red } = parseCode(code);
  const node = el("span", `ideal-chip${red ? " red" : ""}`);
  node.title = code;
  node.innerHTML = `<b>${rank}</b><i>${SUIT_SYM[suit] || "?"}</i>`;
  return node;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
