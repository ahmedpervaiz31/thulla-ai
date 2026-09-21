import { getGame, getGameReview } from "../api/games.js";
import {
  bindConsentModal,
} from "../components/ConsentModal.js";
import {
  bindControlsBar,
} from "../components/ControlsBar.js";
import {
  bindFinishModal,
} from "../components/FinishModal.js";
import { bindSortChips } from "../components/HandRail.js";
import {
  bindIdealMove,
  renderIdealMove,
  setIdealOpen,
  setIdealVisible,
} from "../components/IdealMove.js";
import {
  bindScratchPad,
  setScratchOpen,
} from "../components/ScratchPad.js";
import { bindReviewNav } from "../components/ReviewNav.js";
import { bindHandPeek } from "../components/HandPeek.js";
import { createPacer } from "../pacing/controller.js";
import { gameStore } from "../state/gameStore.js";
import { createAdviceController } from "../table/advice.js";
import { createTableActions } from "../table/actions.js";
import { createTableRenderer } from "../table/render.js";
import { createSidebarController } from "../table/sidebar.js";
import { TABLE_TEMPLATE } from "../table/template.js";

/**
 * Table: subscribe to store, render arena/hand, actions, pacing.
 */
export function createTablePage({ navigate }) {
  let root = null;
  let unsub = null;
  let unbindReviewKeys = null;
  let mounting = false;
  let prevTrickLen = 0;
  let lastRenderKey = null;

  const getRoot = () => root;

  const advice = createAdviceController({ getRoot });

  const sidebar = createSidebarController({
    getRoot,
    refreshAdvice: (...args) => advice.refreshAdvice(...args),
  });

  // Pacer ↔ actions: wire step after both exist.
  let doStepFn = async () => {};
  const pacer = createPacer({
    onStep: (opts) => doStepFn(opts),
  });

  const actions = createTableActions({
    getRoot,
    pacer,
    navigate,
  });
  doStepFn = actions.doStep;

  const renderer = createTableRenderer({
    getRoot,
    getPrevTrickLen: () => prevTrickLen,
    setPrevTrickLen: (n) => {
      prevTrickLen = n;
    },
    getLastRenderKey: () => lastRenderKey,
    setLastRenderKey: (k) => {
      lastRenderKey = k;
    },
    controlsOpts: () => actions.controlsOpts(),
    refreshAdvice: (...args) => advice.refreshAdvice(...args),
    pacer,
  });

  function bindTable(host) {
    host.innerHTML = TABLE_TEMPLATE;
    root = host.querySelector('[data-page="table"]');
    prevTrickLen = 0;
    lastRenderKey = null;

    bindSortChips(root);
    bindControlsBar(root, {
      onPlay: () => actions.playSelected(),
      onStep: () => actions.doStep(),
      onToggleAuto: () => actions.toggleAuto(),
    });
    bindConsentModal(root.querySelector('[data-role="take-modal"]'), {
      onAnswer: actions.onConsent,
    });
    bindFinishModal(root.querySelector('[data-role="finish-modal"]'), {
      onAgain: actions.goLobby,
      onReview: () => actions.enterReview(),
    });
    bindScratchPad(root, {
      onToggle: (open) => {
        sidebar.setSidebar(open ? "scratch" : null);
      },
    });
    bindIdealMove(root, {
      onToggle: (open) => {
        sidebar.setSidebar(open ? "ideal" : null);
      },
    });
    unbindReviewKeys = bindReviewNav(root, {
      onPrev: () => actions.stepReview(-1),
      onNext: () => actions.stepReview(1),
      onLobby: () => actions.goLobby(),
    });
    bindHandPeek(root);
    setScratchOpen(root, false);
    setIdealOpen(root, false);
    const { game: bootGame, reviewMode } = gameStore.getSnapshot();
    setIdealVisible(root, bootGame?.mode === "human" && !reviewMode);
    renderIdealMove(root, null);

    unsub = gameStore.subscribe(() => renderer.render());
    renderer.render();

    if (bootGame?.mode === "human" && !reviewMode && !bootGame?.finished) {
      pacer.schedule();
    }
  }

  return {
    async mount(host, params) {
      const mountGen = (this._mountGen = (this._mountGen || 0) + 1);
      if (mounting) return;
      mounting = true;
      try {
        let { game, reviewMode } = gameStore.getSnapshot();
        const routeId = params?.id;
        const wantReview = Boolean(params?.review);

        if (wantReview && routeId) {
          try {
            const review = await getGameReview(routeId);
            if (mountGen !== this._mountGen) return;
            const frames = review.frames || [];
            if (!frames.length) {
              gameStore.clearSession();
              navigate("/lobby");
              return;
            }
            gameStore.enterReview(frames);
            game = frames[0];
            reviewMode = true;
          } catch {
            if (mountGen !== this._mountGen) return;
            gameStore.clearSession();
            navigate("/lobby");
            return;
          }
        } else if ((!game || (routeId && game.id !== routeId)) && routeId) {
          try {
            const restored = await getGame(routeId);
            if (mountGen !== this._mountGen) return;
            gameStore.clearReview();
            gameStore.setFinishDismissed(false);
            gameStore.setGame(restored, { clearSelection: true });
            gameStore.setAutoEnabled(false);
            game = restored;
            if (restored.finished) {
              // Finished live load → open in review if frames exist.
              try {
                await actions.enterReview({ gameId: routeId });
                game = gameStore.getSnapshot().game;
                reviewMode = true;
              } catch {
                /* stay on finished table with modal */
              }
            }
          } catch {
            if (mountGen !== this._mountGen) return;
            // Completed analysis-only games: try review route.
            try {
              const review = await getGameReview(routeId);
              if (mountGen !== this._mountGen) return;
              const frames = review.frames || [];
              if (!frames.length) throw new Error("empty");
              gameStore.enterReview(frames);
              game = frames[0];
              reviewMode = true;
            } catch {
              if (mountGen !== this._mountGen) return;
              gameStore.clearSession();
              navigate("/lobby");
              return;
            }
          }
        }

        if (mountGen !== this._mountGen) return;

        if (!game || (routeId && game.id !== routeId)) {
          navigate("/lobby");
          return;
        }

        bindTable(host);
      } finally {
        mounting = false;
      }
    },

    unmount() {
      this._mountGen = (this._mountGen || 0) + 1;
      pacer.stop();
      if (unbindReviewKeys) unbindReviewKeys();
      unbindReviewKeys = null;
      if (unsub) unsub();
      unsub = null;
      root = null;
      lastRenderKey = null;
      advice.invalidate();
    },
  };
}
