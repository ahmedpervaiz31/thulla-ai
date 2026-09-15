import {
  DELAY_MIN,
  DELAY_PLAY_TARGET,
  DELAY_REVEAL,
  DELAY_REVEAL_THULLA,
  DELAY_TAKE,
} from "../constants/delays.js";
import { gameStore } from "../state/gameStore.js";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Client-side pace controller.
 * Human mode: auto-steps CPU actions. AI mode: only when AUTO is on.
 *
 * CPU *plays*: run the step, then pad so think+pad ≈ DELAY_PLAY_TARGET.
 * Take / give / reveal: pre-delay beat (take/give may credit prior take think).
 * Take requests are never padded to the play target.
 */
export function createPacer({ onStep }) {
  let paceTimer = null;
  let pacing = false;
  let thinkCreditMs = 0;
  let rafId = 0;

  function clearTimer() {
    if (paceTimer) clearTimeout(paceTimer);
    paceTimer = null;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = 0;
  }

  function stop() {
    clearTimer();
    pacing = false;
    thinkCreditMs = 0;
  }

  function isPacing() {
    return pacing;
  }

  function needsClientPace() {
    const { game, autoEnabled } = gameStore.getSnapshot();
    if (!game || game.finished) return false;
    const p = game.pending;
    if (!p) return false;
    if (p.type === "reveal") return true;
    if (p.type === "play" || p.type === "take" || p.type === "give") {
      const cpu = !game.seats[p.seat]?.is_human;
      if (!cpu) return false;
      if (game.mode === "human") return true;
      return Boolean(autoEnabled);
    }
    return false;
  }

  function pendingType() {
    return gameStore.getSnapshot().game?.pending?.type || null;
  }

  /** Pre-wait before take / give / reveal only. Plays start after paint. */
  function delayBeforeStep() {
    const { game } = gameStore.getSnapshot();
    const type = game?.pending?.type;
    if (type === "play") {
      thinkCreditMs = 0;
      return 0;
    }
    let base = DELAY_TAKE;
    if (type === "reveal") {
      const thulla = (game.last_event || "").toUpperCase().includes("THULLA");
      base = thulla ? DELAY_REVEAL_THULLA : DELAY_REVEAL;
    }
    const credit = thinkCreditMs;
    thinkCreditMs = 0;
    return Math.max(DELAY_MIN, base - credit);
  }

  function schedule() {
    clearTimer();
    if (!needsClientPace()) {
      pacing = false;
      thinkCreditMs = 0;
      return;
    }
    pacing = true;
    const typeAtArm = pendingType();
    const wait = delayBeforeStep();
    // Double-rAF: let the browser paint whose_turn / pot before the wait.
    rafId = requestAnimationFrame(() => {
      rafId = requestAnimationFrame(() => {
        rafId = 0;
        paceTimer = setTimeout(async () => {
          const t0 = performance.now();
          try {
            await onStep({ quiet: true });
          } catch (err) {
            console.warn(err);
          }
          const elapsed = performance.now() - t0;

          if (typeAtArm === "play") {
            // Standardize play wall-clock; do not bleed credit into take pacing.
            const pad = Math.max(0, DELAY_PLAY_TARGET - elapsed);
            if (pad > 0) await sleep(pad);
            thinkCreditMs = 0;
          } else {
            thinkCreditMs = elapsed;
          }
          schedule();
        }, wait);
      });
    });
  }

  return { schedule, stop, needsClientPace, isPacing };
}
