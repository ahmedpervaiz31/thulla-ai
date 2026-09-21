import { answerConsent, getGameReview, playCard, stepGame } from "../api/games.js";
import { updateControlsBar } from "../components/ControlsBar.js";
import { gameStore } from "../state/gameStore.js";

/**
 * Play / step / consent / auto actions for the table.
 * @param {{
 *   getRoot: () => HTMLElement|null,
 *   pacer: { schedule: Function, stop: Function, isPacing: () => boolean },
 *   navigate: (path: string) => void,
 * }} ctx
 */
export function createTableActions(ctx) {
  let stepInFlight = false;
  let reviewLoading = false;

  function controlsOpts() {
    return {
      pacing: ctx.pacer.isPacing(),
      stepBusy: stepInFlight,
      reviewMode: gameStore.getSnapshot().reviewMode,
    };
  }

  function isStepBusy() {
    return stepInFlight;
  }

  async function doStep(opts = {}) {
    const root = ctx.getRoot();
    const { game, reviewMode } = gameStore.getSnapshot();
    if (!game || game.finished || reviewMode || stepInFlight) return;
    stepInFlight = true;
    if (root) updateControlsBar(root, controlsOpts());
    try {
      const next = await stepGame(game.id);
      gameStore.setGame(next, { clearSelection: true });
      if (next.finished) {
        gameStore.setAutoEnabled(false);
        ctx.pacer.stop();
      }
    } catch (err) {
      gameStore.setAutoEnabled(false);
      ctx.pacer.stop();
      if (!opts.quiet) alert(err.message);
      else throw err;
    } finally {
      stepInFlight = false;
      const r = ctx.getRoot();
      if (r) updateControlsBar(r, controlsOpts());
    }
  }

  async function playSelected() {
    const root = ctx.getRoot();
    const { game, selectedCard, reviewMode } = gameStore.getSnapshot();
    if (!selectedCard || !game || reviewMode) return;
    const playBtn = root?.querySelector('[data-role="play-btn"]');
    if (playBtn) playBtn.disabled = true;
    try {
      const next = await playCard(game.id, selectedCard);
      gameStore.setGame(next, { clearSelection: true });
      ctx.pacer.schedule();
    } catch (err) {
      alert(err.message);
      if (root) updateControlsBar(root, controlsOpts());
    }
  }

  async function onConsent(accept) {
    const { game, reviewMode } = gameStore.getSnapshot();
    if (!game?.pending || reviewMode) return;
    const kind = game.pending.type;
    if (kind !== "take" && kind !== "give") return;
    try {
      const next = await answerConsent(game.id, kind, accept);
      gameStore.setGame(next, { clearSelection: true });
      ctx.pacer.schedule();
    } catch (err) {
      alert(err.message);
    }
  }

  function toggleAuto() {
    const { autoEnabled, reviewMode } = gameStore.getSnapshot();
    if (reviewMode) return;
    if (autoEnabled) {
      gameStore.setAutoEnabled(false);
      ctx.pacer.stop();
      return;
    }
    gameStore.setAutoEnabled(true);
    ctx.pacer.schedule();
  }

  function goLobby() {
    ctx.pacer.stop();
    gameStore.clearSession();
    ctx.navigate("/lobby");
  }

  async function enterReview(opts = {}) {
    if (reviewLoading) return;
    const { game, reviewMode, reviewFrames } = gameStore.getSnapshot();
    if (reviewMode && reviewFrames?.length) {
      gameStore.setFinishDismissed(true);
      return;
    }
    const id = opts.gameId || game?.id;
    if (!id) return;
    reviewLoading = true;
    ctx.pacer.stop();
    gameStore.setAutoEnabled(false);
    try {
      const review = await getGameReview(id);
      const frames = review.frames || [];
      if (!frames.length) {
        alert("No review frames available for this game.");
        return;
      }
      gameStore.enterReview(frames, { index: opts.index });
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      reviewLoading = false;
    }
  }

  function stepReview(delta) {
    gameStore.stepReview(delta);
  }

  return {
    doStep,
    playSelected,
    onConsent,
    toggleAuto,
    goLobby,
    enterReview,
    stepReview,
    isStepBusy,
    controlsOpts,
  };
}
