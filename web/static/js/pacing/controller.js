import { DELAY_PLAY, DELAY_REVEAL, DELAY_TAKE } from "../constants/delays.js";
import { gameStore } from "../state/gameStore.js";

/**
 * Client-side pace controller.
 * Human mode: auto-steps CPU actions. AI mode: only when AUTO is on.
 * Delays: play ~750ms, reveal ~2200ms, take/give ~550ms.
 *
 * `pacing` is local (not store) so timer arming does not rebuild the table.
 */
export function createPacer({ onStep }) {
  let paceTimer = null;
  let pacing = false;

  function stop() {
    if (paceTimer) clearTimeout(paceTimer);
    paceTimer = null;
    pacing = false;
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

  function delayForPending() {
    const { game } = gameStore.getSnapshot();
    if (!game?.pending) return DELAY_PLAY;
    if (game.pending.type === "reveal") return DELAY_REVEAL;
    if (game.pending.type === "take" || game.pending.type === "give") {
      return DELAY_TAKE;
    }
    return DELAY_PLAY;
  }

  function schedule() {
    stop();
    if (!needsClientPace()) return;
    pacing = true;
    paceTimer = setTimeout(async () => {
      try {
        await onStep({ quiet: true });
      } catch (err) {
        console.warn(err);
      }
      schedule();
    }, delayForPending());
  }

  return { schedule, stop, needsClientPace, isPacing };
}
