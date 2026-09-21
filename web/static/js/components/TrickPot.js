import { LEAD_TO_CODE, SUIT_NAME, SUIT_SYM } from "../constants/suits.js";
import { isThullaReveal } from "../lib/game.js";
import { createCardEl } from "./Card.js";

/**
 * Trick pot + lead/pot labels + rule hint + event banner.
 * Diffs the pot DOM so existing cards are not rebuilt (no reload flicker).
 */
export function renderTrickPot(root, game, prevTrickLen) {
  const leadLabel = root.querySelector('[data-role="lead-label"]');
  const potLabel = root.querySelector('[data-role="pot-label"]');
  const trickBox = root.querySelector('[data-role="trick-box"]');
  const trickCards = root.querySelector('[data-role="trick-cards"]');
  const ruleHint = root.querySelector('[data-role="rule-hint"]');
  const eventBanner = root.querySelector('[data-role="event-banner"]');

  const lead = game.trick?.lead_suit;
  leadLabel.textContent = lead
    ? `LEAD: ${SUIT_SYM[LEAD_TO_CODE[lead]] || ""} ${SUIT_NAME[lead] || lead}`
    : "LEAD: —";
  potLabel.textContent = `POT: ${game.trick?.cards?.length || 0}`;

  const revealing = game.phase === "trick_reveal";
  const thullaReveal = isThullaReveal(game);
  trickBox.classList.toggle("revealing", revealing);
  trickBox.classList.toggle("thulla", thullaReveal);

  const cards = game.trick?.cards || [];
  const existing = [...trickCards.querySelectorAll(".trick-play")];
  const signature = (p) => `${p.player}|${p.card}`;

  let samePrefix = existing.length > 0 && existing.length <= cards.length;
  if (samePrefix) {
    for (let i = 0; i < existing.length; i++) {
      if (existing[i].dataset.sig !== signature(cards[i])) {
        samePrefix = false;
        break;
      }
    }
  }

  if (!samePrefix) {
    trickCards.innerHTML = "";
    cards.forEach((p, i) => {
      trickCards.appendChild(
        makeTrickPlay(p, i >= prevTrickLen, i === cards.length - 1 && i >= prevTrickLen)
      );
    });
  } else if (cards.length < existing.length) {
    for (let i = existing.length - 1; i >= cards.length; i--) {
      existing[i].remove();
    }
  } else {
    existing.forEach((el) => el.classList.remove("fresh"));
    for (let i = existing.length; i < cards.length; i++) {
      trickCards.appendChild(
        makeTrickPlay(cards[i], i >= prevTrickLen, i === cards.length - 1)
      );
    }
  }

  let nextPrev = cards.length;
  if (
    game.phase !== "first_trick" &&
    game.phase !== "trick" &&
    game.phase !== "trick_reveal"
  ) {
    nextPrev = 0;
    if (cards.length === 0) trickCards.innerHTML = "";
  }

  if (game.phase === "trick_reveal") {
    ruleHint.textContent = game.last_event || "Holding pot…";
  } else if (
    game.pending?.type === "play" &&
    game.pending.lead_suit &&
    game.pending.must_follow
  ) {
    const s = game.pending.lead_suit;
    ruleHint.textContent = `SUIT RULE: Must follow ${SUIT_NAME[s] || s} if you hold one.`;
  } else if (game.pending?.type === "play" && game.trick?.first_trick) {
    ruleHint.textContent =
      "FIRST TRICK: Ace of Spades opens (no thulla pickup).";
  } else if (game.pending?.type === "play" && !game.pending.lead_suit) {
    ruleHint.textContent = "LEAD any card.";
  } else {
    ruleHint.textContent = "";
  }

  let banner = game.last_event || "";
  if (game.phase === "trick_reveal") {
    banner = game.last_event || "TRICK COMPLETE";
  }
  if (game.finished) banner = "";

  const prevBanner = eventBanner.dataset.text || "";
  eventBanner.dataset.text = banner;
  eventBanner.classList.toggle("thulla-banner", thullaReveal);
  if (banner !== prevBanner) {
    eventBanner.classList.remove("show");
    eventBanner.textContent = banner;
    if (banner) {
      // Retrigger fade-in when copy changes.
      void eventBanner.offsetWidth;
      eventBanner.classList.add("show");
    }
  } else {
    eventBanner.textContent = banner;
    eventBanner.classList.toggle("show", Boolean(banner));
  }

  // TablePage may override for AI take/give prompts when AUTO is off.
  return { prevTrickLen: nextPrev, eventBanner };
}

function makeTrickPlay(play, dealIn, fresh) {
  const wrap = document.createElement("div");
  wrap.className = "trick-play";
  if (fresh) wrap.classList.add("fresh");
  wrap.dataset.sig = `${play.player}|${play.card}`;

  const label = document.createElement("div");
  label.className = "trick-play-label";
  label.textContent = play.player;
  wrap.appendChild(label);

  wrap.appendChild(createCardEl(play.card, { small: true, dealIn }));
  return wrap;
}
