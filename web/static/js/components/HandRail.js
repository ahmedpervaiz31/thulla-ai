import { SORT_RANK, SORT_SUIT } from "../constants/lobby.js";
import { sortHand } from "../lib/cards.js";
import { ordinal } from "../lib/ordinal.js";
import { gameStore } from "../state/gameStore.js";
import { createCardEl } from "./Card.js";

/**
 * YOU rail + hand cards + sort chips wiring helpers.
 */
export function renderYouBar(railRoot, seat, whoseTurn) {
  if (!seat) {
    railRoot.classList.add("hidden");
    return;
  }
  railRoot.classList.remove("hidden");
  railRoot.classList.toggle("turn", whoseTurn === seat.seat && seat.active);
  railRoot.classList.toggle("out", !seat.active);

  const nameEl = railRoot.querySelector('[data-role="you-name"]');
  const metaEl = railRoot.querySelector('[data-role="you-meta"]');
  nameEl.textContent = seat.name.toUpperCase();
  if (!seat.active) {
    metaEl.textContent = seat.place
      ? `OUT • ${seat.place}${ordinal(seat.place)}`
      : "OUT";
  } else {
    metaEl.textContent = `${seat.hand_size} CARDS`;
  }
}

/**
 * Full hand rebuild (deal / sort / play). Prefer updateHandSelection for picks.
 */
export function renderHand(handEl, { onSelect }) {
  const { game, selectedCard, sortMode } = gameStore.getSnapshot();
  handEl.innerHTML = "";
  if (!game || game.your_hand == null) return;

  const legal = new Set(game.legal_moves || []);
  const awaitingPlay =
    game.pending &&
    game.pending.type === "play" &&
    game.seats[game.pending.seat]?.is_human;

  sortHand(game.your_hand, sortMode).forEach((code) => {
    const isLegal = awaitingPlay && legal.has(code);
    handEl.appendChild(
      createCardEl(code, {
        legal: isLegal,
        selected: selectedCard === code,
        dim: awaitingPlay && !isLegal,
        showTag: isLegal,
        onClick: () => {
          if (!isLegal) return;
          onSelect(code);
        },
      })
    );
  });

  syncHandRailWidth(handEl);
}

/** Toggle selected class without wiping the hand DOM. */
export function updateHandSelection(handEl) {
  const { selectedCard } = gameStore.getSnapshot();
  handEl.querySelectorAll(".playing-card").forEach((el) => {
    el.classList.toggle("selected", el.dataset.code === selectedCard);
  });
}

/** Size the YOU rail and scale cards so one row fits with no scroll. */
export function syncHandRailWidth(handEl) {
  const rail = handEl.closest(".you-rail");
  const zone = handEl.closest(".hand-zone");
  if (!rail) return;

  const cards = [...handEl.querySelectorAll(".playing-card")];
  const n = cards.length;
  const padX = 24;
  const maxW = Math.min(
    920,
    Math.max(220, (zone?.clientWidth || rail.parentElement?.clientWidth || 920) - 8)
  );

  const baseW = 58;
  const baseH = 82;
  const baseGap = 8;
  let cardW = baseW;
  let gap = baseGap;

  if (n > 0) {
    const avail = maxW - padX;
    const full = n * baseW + Math.max(0, n - 1) * baseGap;
    if (full > avail) {
      // Shrink gap first, then card width, keep a readable minimum.
      gap = Math.max(2, Math.min(baseGap, Math.floor((avail - n * 36) / Math.max(1, n - 1))));
      cardW = Math.max(36, Math.floor((avail - Math.max(0, n - 1) * gap) / n));
    }
  }

  const cardH = Math.round(cardW * (baseH / baseW));
  const rankPx = Math.max(10, Math.round(cardW * 0.28));
  const suitPx = Math.max(12, Math.round(cardW * 0.38));

  handEl.style.gap = `${gap}px`;
  cards.forEach((el) => {
    el.style.width = `${cardW}px`;
    el.style.height = `${cardH}px`;
    const rank = el.querySelector(".rank");
    const suit = el.querySelector(".suit");
    if (rank) rank.style.fontSize = `${rankPx}px`;
    if (suit) suit.style.fontSize = `${suitPx}px`;
  });

  const inner = n > 0 ? n * cardW + Math.max(0, n - 1) * gap + padX : 220;
  rail.style.width = `${Math.min(maxW, Math.max(220, inner))}px`;
}

export function syncSortChips(root) {
  const { sortMode } = gameStore.getSnapshot();
  const suitBtn = root.querySelector('[data-role="sort-suit"]');
  const rankBtn = root.querySelector('[data-role="sort-rank"]');
  if (!suitBtn || !rankBtn) return;
  suitBtn.classList.toggle("on", sortMode === SORT_SUIT);
  rankBtn.classList.toggle("on", sortMode === SORT_RANK);
}

export function bindSortChips(root, { onChange }) {
  root.querySelector('[data-role="sort-suit"]').addEventListener("click", () => {
    gameStore.setSortMode(SORT_SUIT);
    onChange();
  });
  root.querySelector('[data-role="sort-rank"]').addEventListener("click", () => {
    gameStore.setSortMode(SORT_RANK);
    onChange();
  });
}
