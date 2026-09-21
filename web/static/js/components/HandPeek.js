import { createCardEl } from "./Card.js";
import { sortHand } from "../lib/cards.js";
import { gameStore } from "../state/gameStore.js";

/**
 * Review-mode peek modal: show another seat's full hand.
 */

export function renderHandPeek(root) {
  const modal = root.querySelector('[data-role="hand-peek"]');
  if (!modal) return;

  const { game, reviewMode, sortMode, peekSeat } = gameStore.getSnapshot();
  if (!reviewMode || peekSeat == null || !game) {
    modal.classList.add("hidden");
    modal.classList.remove("is-open");
    return;
  }

  const seat = game.seats?.[peekSeat];
  if (!seat || seat.is_human) {
    modal.classList.add("hidden");
    modal.classList.remove("is-open");
    return;
  }

  const title = modal.querySelector('[data-role="hand-peek-title"]');
  const body = modal.querySelector('[data-role="hand-peek-body"]');
  const meta = modal.querySelector('[data-role="hand-peek-meta"]');
  if (title) title.textContent = `${(seat.name || "PLAYER").toUpperCase()} HAND`;
  if (meta) {
    meta.textContent = seat.active
      ? `${seat.hand_size ?? (seat.hand || []).length} CARDS`
      : seat.place
        ? `OUT • ${seat.place}`
        : "OUT";
  }

  body.innerHTML = "";
  const hand = Array.isArray(seat.hand) ? seat.hand : [];
  if (!hand.length) {
    const empty = document.createElement("p");
    empty.className = "hand-peek-empty";
    if (seat.hand_size === 0) {
      empty.textContent = "EMPTY HAND";
    } else {
      empty.textContent = "HAND UNAVAILABLE";
    }
    body.appendChild(empty);
  } else {
    sortHand(hand, sortMode).forEach((code) => {
      body.appendChild(createCardEl(code, { small: true }));
    });
  }

  const wasHidden = modal.classList.contains("hidden");
  modal.classList.remove("hidden");
  if (wasHidden) {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => modal.classList.add("is-open"));
    });
  } else {
    modal.classList.add("is-open");
  }
}

export function bindHandPeek(root, { onClose } = {}) {
  const modal = root.querySelector('[data-role="hand-peek"]');
  if (!modal) return;

  modal.querySelectorAll('[data-role="hand-peek-close"]').forEach((el) => {
    el.addEventListener("click", () => {
      closeHandPeek(modal);
      onClose?.();
      gameStore.setPeekSeat(null);
    });
  });
}

function closeHandPeek(modal) {
  modal.classList.remove("is-open");
  const done = () => {
    modal.classList.add("hidden");
    modal.removeEventListener("transitionend", done);
  };
  modal.addEventListener("transitionend", done);
  // Fallback if transitionend doesn't fire.
  setTimeout(() => modal.classList.add("hidden"), 280);
}
