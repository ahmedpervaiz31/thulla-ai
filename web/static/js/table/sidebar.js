import { syncHandRailWidth } from "../components/HandRail.js";
import {
  panelTransitionMs,
  setIdealOpen,
} from "../components/IdealMove.js";
import { setScratchOpen } from "../components/ScratchPad.js";
import { sleep } from "../lib/async.js";

/**
 * Mutual-exclusion sidebar open/close for Ideal + Scratch.
 * @param {{
 *   getRoot: () => HTMLElement|null,
 *   refreshAdvice: (force?: boolean) => Promise<void>|void,
 * }} ctx
 */
export function createSidebarController(ctx) {
  let sidebarBusy = false;

  function syncHandAfterSidebar() {
    const root = ctx.getRoot();
    const hand = root?.querySelector('[data-role="hand"]');
    if (!hand) return;
    requestAnimationFrame(() => syncHandRailWidth(hand));
    setTimeout(() => syncHandRailWidth(hand), panelTransitionMs() + 20);
  }

  /**
   * Only one sidebar open. Closing the other recenters before opening.
   * @param {"scratch"|"ideal"|null} which
   */
  async function setSidebar(which) {
    const root = ctx.getRoot();
    if (!root || sidebarBusy) return;
    const wantScratch = which === "scratch";
    const wantIdeal = which === "ideal";
    const scratchOpen = root.classList.contains("scratch-open");
    const idealOpen = root.classList.contains("ideal-open");

    if (wantScratch === scratchOpen && wantIdeal === idealOpen) {
      if (wantIdeal) ctx.refreshAdvice(true);
      return;
    }

    sidebarBusy = true;
    try {
      const closingOther =
        (wantScratch && idealOpen) || (wantIdeal && scratchOpen) || which === null;

      if (scratchOpen && !wantScratch) setScratchOpen(root, false);
      if (idealOpen && !wantIdeal) setIdealOpen(root, false);

      if (closingOther && (scratchOpen || idealOpen)) {
        await sleep(panelTransitionMs());
      }

      if (wantScratch) setScratchOpen(root, true);
      if (wantIdeal) {
        setIdealOpen(root, true);
        await ctx.refreshAdvice(true);
      }
      syncHandAfterSidebar();
    } finally {
      sidebarBusy = false;
    }
  }

  return { setSidebar };
}
