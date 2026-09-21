import { isThullaReveal } from "../lib/game.js";
import { seatSlots } from "../lib/seats.js";
import { fillSeatSlot } from "../components/SeatChip.js";
import {
  renderHand,
  renderYouBar,
  syncSortChips,
  updateHandSelection,
} from "../components/HandRail.js";
import { updateControlsBar } from "../components/ControlsBar.js";
import { renderConsentModal } from "../components/ConsentModal.js";
import { renderFinishModal } from "../components/FinishModal.js";
import { renderScratchPad } from "../components/ScratchPad.js";
import {
  setIdealVisible,
} from "../components/IdealMove.js";
import { renderReviewNav } from "../components/ReviewNav.js";
import { renderHandPeek } from "../components/HandPeek.js";
import { updateTopBar } from "../components/TopBar.js";
import { renderTrickPot } from "../components/TrickPot.js";
import { gameStore } from "../state/gameStore.js";
import { gameRevision } from "./advice.js";

export function applyAiBannerOverrides(eventBanner, game, autoEnabled) {
  if (game.finished) {
    eventBanner.textContent = "";
    eventBanner.dataset.text = "";
    eventBanner.classList.remove("show", "thulla-banner");
    return;
  }
  if (game.phase === "trick_reveal") {
    // TrickPot already set banner + show class.
    return;
  }
  let text = "";
  if (game.mode === "ai" && !autoEnabled && game.pending?.type === "take") {
    text = `${game.seats[game.pending.seat].name}: ask ${game.pending.target_name} for ${game.pending.n_cards}? (NEXT STEP)`;
  } else if (
    game.mode === "ai" &&
    !autoEnabled &&
    game.pending?.type === "give"
  ) {
    text = `${game.seats[game.pending.seat].name}: give to ${game.pending.asker_name}? (NEXT STEP)`;
  }
  if (!text) return;
  eventBanner.dataset.text = text;
  eventBanner.textContent = text;
  eventBanner.classList.remove("thulla-banner");
  eventBanner.classList.add("show");
}

export function sizeCenterForPlayers(root, n) {
  const center = root.querySelector(".center-zone");
  if (!center) return;
  const slots = Math.max(3, Math.min(8, n || 4));
  center.style.setProperty("--pot-slots", String(slots));
}

function renderKey(snap) {
  const reviewBit = snap.reviewMode
    ? `review:${snap.reviewIndex}/${snap.reviewFrames?.length || 0}`
    : "live";
  return `${gameRevision(snap.game)}|sort:${snap.sortMode}|${reviewBit}|fd:${snap.finishDismissed ? 1 : 0}|peek:${snap.peekSeat ?? ""}`;
}

/**
 * Arena / hand / controls paint for the table page.
 * @param {{
 *   getRoot: () => HTMLElement|null,
 *   getPrevTrickLen: () => number,
 *   setPrevTrickLen: (n: number) => void,
 *   getLastRenderKey: () => string|null,
 *   setLastRenderKey: (k: string|null) => void,
 *   controlsOpts: () => object,
 *   refreshAdvice: (force?: boolean) => void,
 *   pacer: { isPacing: () => boolean, stop: () => void },
 * }} ctx
 */
export function createTableRenderer(ctx) {
  let rendering = false;

  function renderSelectionOnly() {
    const root = ctx.getRoot();
    if (!root) return;
    const snap = gameStore.getSnapshot();
    const { game, autoEnabled, reviewMode } = snap;
    updateHandSelection(root.querySelector('[data-role="hand"]'));
    updateControlsBar(root, ctx.controlsOpts());
    renderReviewNav(root, snap);
    if (game && !reviewMode) {
      const eventBanner = root.querySelector('[data-role="event-banner"]');
      if (eventBanner) applyAiBannerOverrides(eventBanner, game, autoEnabled);
    }
  }

  function render() {
    const root = ctx.getRoot();
    if (!root || rendering) return;
    const snap = gameStore.getSnapshot();
    const { game, autoEnabled, reviewMode, finishDismissed } = snap;
    if (!game) return;

    const key = renderKey(snap);
    if (key === ctx.getLastRenderKey()) {
      renderSelectionOnly();
      return;
    }

    rendering = true;
    try {
      updateTopBar(game, { reviewMode });

      const { prevTrickLen: nextLen, eventBanner } = renderTrickPot(
        root,
        game,
        ctx.getPrevTrickLen()
      );
      if (!reviewMode) {
        applyAiBannerOverrides(eventBanner, game, autoEnabled);
      }
      ctx.setPrevTrickLen(nextLen);

      const n = game.seats.length;
      const humanMode = game.mode === "human";
      const slots = seatSlots(n, humanMode);
      const arena = root.querySelector('[data-role="arena"]');

      root.classList.toggle("human-mode", humanMode);
      root.classList.toggle("ai-mode", !humanMode);
      root.classList.toggle("review-mode", reviewMode);
      arena.classList.toggle("human-table", humanMode);
      arena.dataset.players = String(n);
      sizeCenterForPlayers(root, n);

      const turnOpts = {
        turnLabel: isThullaReveal(game) ? "THULLA" : "TURN",
        reviewMode,
      };

      fillSeatSlot(
        root.querySelector('[data-slot="top"]'),
        slots.top,
        "top",
        game.seats,
        game.whose_turn,
        turnOpts
      );
      fillSeatSlot(
        root.querySelector('[data-slot="left"]'),
        slots.left,
        "left",
        game.seats,
        game.whose_turn,
        turnOpts
      );
      fillSeatSlot(
        root.querySelector('[data-slot="right"]'),
        slots.right,
        "right",
        game.seats,
        game.whose_turn,
        turnOpts
      );

      const youRail = root.querySelector('[data-role="you-rail"]');
      if (humanMode) {
        fillSeatSlot(
          root.querySelector('[data-slot="bottom"]'),
          null,
          "bottom",
          game.seats,
          game.whose_turn,
          turnOpts
        );
        renderYouBar(youRail, game.seats[0], game.whose_turn, turnOpts);
      } else {
        fillSeatSlot(
          root.querySelector('[data-slot="bottom"]'),
          slots.bottom,
          "bottom",
          game.seats,
          game.whose_turn,
          turnOpts
        );
        youRail.classList.add("hidden");
      }

      renderHand(root.querySelector('[data-role="hand"]'), {
        onSelect: (code) => {
          if (gameStore.getSnapshot().reviewMode) return;
          const cur = gameStore.getSnapshot().selectedCard;
          gameStore.setSelectedCard(cur === code ? null : code);
        },
      });
      updateHandSelection(root.querySelector('[data-role="hand"]'));
      syncSortChips(root);
      updateControlsBar(root, ctx.controlsOpts());
      renderConsentModal(
        root.querySelector('[data-role="take-modal"]'),
        reviewMode ? { ...game, pending: null } : game
      );
      renderFinishModal(root.querySelector('[data-role="finish-modal"]'), game, {
        dismissed: finishDismissed,
        reviewMode,
      });
      renderScratchPad(root, game);
      renderReviewNav(root, snap);
      renderHandPeek(root);
      setIdealVisible(root, humanMode && !reviewMode);
      if (humanMode && !reviewMode && root.classList.contains("ideal-open")) {
        ctx.refreshAdvice(false);
      }

      ctx.setLastRenderKey(key);

      if (game.finished && !reviewMode) {
        gameStore.setAutoEnabled(false);
        ctx.pacer.stop();
      }
    } finally {
      rendering = false;
    }
  }

  return { render };
}
