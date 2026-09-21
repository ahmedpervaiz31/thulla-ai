import { LEAD_TO_CODE, SUIT_NAME, SUIT_SYM } from "../constants/suits.js";
import { parseCode } from "../lib/cards.js";
import { el } from "../lib/dom.js";
import { bindEdgePad, setPadOpen } from "../lib/edgePad.js";

// Matches CSS token --pad-ms (0.22s).
const PANEL_MS = 220;

/**
 * Left-edge ideal-move coach (human mode). Mutual exclusion with scratch pad
 * is owned by TablePage via setIdealOpen / onToggle.
 */
export function bindIdealMove(root, { onToggle } = {}) {
  bindEdgePad(root, {
    handleRole: "ideal-toggle",
    openClass: "ideal-open",
    openSign: 1,
    onToggle,
  });
}

export function setIdealOpen(root, open) {
  setPadOpen(root, "ideal-open", "ideal-toggle", open, {
    openTitle: "Open ideal move",
    closeTitle: "Close ideal move",
  });
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

  if (advice.exact_line?.length) {
    body.appendChild(renderExactLine(advice));
  }
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

function renderExactLine(advice) {
  const sec = el("section", "ideal-section");
  const win = advice.outcome === 1;
  const lose = advice.outcome === -1;
  sec.appendChild(
    el(
      "h3",
      "ideal-h",
      win ? "FORCED WIN LINE" : lose ? "BEST LOSE LINE" : "EXACT LINE"
    )
  );
  const list = el("ol", "ideal-exact-line");
  for (const step of advice.exact_line) {
    const li = el("li", "ideal-exact-step");
    if (!step.card) {
      li.appendChild(el("span", "ideal-exact-note", step.note || ""));
    } else {
      const who = step.side === "you" ? "You" : "Opp";
      li.appendChild(el("span", "ideal-exact-who", who));
      li.appendChild(chip(step.card));
      if (step.note) {
        li.appendChild(el("span", "ideal-exact-note", step.note));
      }
    }
    list.appendChild(li);
  }
  sec.appendChild(list);
  const tip = el(
    "p",
    "ideal-note",
    "Both sides optimal from complete info — compare to how the game actually went."
  );
  sec.appendChild(tip);
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

