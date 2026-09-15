import { getGame, getAdvice, answerConsent, playCard, stepGame } from "../api/games.js";
import {
  bindConsentModal,
  renderConsentModal,
} from "../components/ConsentModal.js";
import {
  bindControlsBar,
  updateControlsBar,
} from "../components/ControlsBar.js";
import {
  bindFinishModal,
  renderFinishModal,
} from "../components/FinishModal.js";
import {
  bindSortChips,
  renderHand,
  renderYouBar,
  syncHandRailWidth,
  syncSortChips,
  updateHandSelection,
} from "../components/HandRail.js";
import {
  bindIdealMove,
  panelTransitionMs,
  renderIdealMove,
  setIdealOpen,
  setIdealVisible,
} from "../components/IdealMove.js";
import {
  bindScratchPad,
  renderScratchPad,
  setScratchOpen,
} from "../components/ScratchPad.js";
import { fillSeatSlot } from "../components/SeatChip.js";
import { updateTopBar } from "../components/TopBar.js";
import { renderTrickPot } from "../components/TrickPot.js";
import { seatSlots } from "../lib/seats.js";
import { createPacer } from "../pacing/controller.js";
import { gameStore } from "../state/gameStore.js";

const TEMPLATE = `
<main class="table" data-page="table">
  <aside class="ideal-pad hidden" data-role="ideal-pad" aria-label="Ideal move coach">
    <button
      type="button"
      class="ideal-handle"
      data-role="ideal-toggle"
      aria-expanded="false"
      aria-controls="ideal-panel"
      title="Open ideal move"
    ></button>
    <div class="ideal-panel" id="ideal-panel" data-role="ideal-panel">
      <div class="ideal-head">
        <span class="ideal-title">IDEAL MOVE</span>
        <span class="ideal-sub">BOT MODEL</span>
      </div>
      <div class="ideal-body" data-role="ideal-body"></div>
    </div>
  </aside>

  <div class="table-shell" data-role="table-shell">
    <div class="arena" data-role="arena">
      <div class="seat seat-top" data-slot="top"></div>
      <div class="seat seat-left" data-slot="left"></div>
      <div class="center-zone">
        <div class="event-banner" data-role="event-banner"></div>
        <div class="trick-box" data-role="trick-box">
          <div class="trick-meta">
            <span data-role="lead-label">LEAD: —</span>
            <span data-role="pot-label">POT: 0</span>
          </div>
          <div class="trick-cards" data-role="trick-cards"></div>
        </div>
        <p class="rule-hint" data-role="rule-hint"></p>
      </div>
      <div class="seat seat-right" data-slot="right"></div>
      <div class="seat seat-bottom" data-slot="bottom"></div>
    </div>

    <div class="hand-zone" data-role="hand-zone">
      <div class="you-rail hidden" data-role="you-rail">
        <div class="you-bar">
          <span class="you-bar-name" data-role="you-name">YOU</span>
          <span class="you-bar-meta" data-role="you-meta">0 CARDS</span>
          <span class="you-bar-turn">TURN</span>
        </div>
        <div class="hand" data-role="hand"></div>
      </div>
    </div>

    <div class="take-modal hidden" data-role="take-modal">
      <p data-role="take-text">Take neighbor's cards?</p>
      <div class="take-actions">
        <button type="button" class="action-btn yes" data-role="take-yes">YES</button>
        <button type="button" class="action-btn no" data-role="take-no">NO</button>
      </div>
    </div>

    <div class="finish-modal hidden" data-role="finish-modal">
      <h2>GAME OVER</h2>
      <ol data-role="finish-list"></ol>
      <button type="button" class="start-btn" data-role="again-btn">▶ BACK TO LOBBY</button>
    </div>

    <footer class="controls" data-role="controls">
      <div class="ctrl-left">
        <button type="button" class="chip" data-role="sort-suit">SUIT</button>
        <button type="button" class="chip" data-role="sort-rank">RANK</button>
      </div>
      <div class="ctrl-center">
        <button type="button" class="play-btn" data-role="play-btn" disabled>▶ PLAY SELECTED</button>
        <button type="button" class="play-btn secondary hidden" data-role="step-btn">▶ NEXT STEP</button>
        <button type="button" class="chip hidden" data-role="auto-btn">AUTO</button>
      </div>
      <div class="ctrl-right">
        <span class="status" data-role="status-text">STATUS: —</span>
      </div>
    </footer>
  </div>

  <aside class="scratch-pad" data-role="scratch-pad" aria-label="Public intel scratch pad">
    <button
      type="button"
      class="scratch-handle"
      data-role="scratch-toggle"
      aria-expanded="false"
      aria-controls="scratch-panel"
      title="Open scratch pad"
    ></button>
    <div class="scratch-panel" id="scratch-panel" data-role="scratch-panel">
      <div class="scratch-head">
        <span class="scratch-title">SCRATCH PAD</span>
        <span class="scratch-sub">PUBLIC INFO</span>
      </div>
      <div class="scratch-body" data-role="scratch-body"></div>
    </div>
  </aside>
</main>
`;

/**
 * Table: subscribe to store, render arena/hand, actions, pacing.
 */
export function createTablePage({ navigate }) {
  let root = null;
  let unsub = null;
  let rendering = false;
  let mounting = false;
  /** Trick deal-in animation cursor (local; not shared store state). */
  let prevTrickLen = 0;
  /** Last layout key used for full render (skip pot rebuild on select). */
  let lastRenderKey = null;
  /** Sidebar switch in progress (mutual exclusion animation). */
  let sidebarBusy = false;
  let adviceCacheKey = null;
  let adviceFetchGen = 0;

  const pacer = createPacer({
    onStep: (opts) => doStep(opts),
  });

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function syncHandAfterSidebar() {
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
    if (!root || sidebarBusy) return;
    const wantScratch = which === "scratch";
    const wantIdeal = which === "ideal";
    const scratchOpen = root.classList.contains("scratch-open");
    const idealOpen = root.classList.contains("ideal-open");

    if (wantScratch === scratchOpen && wantIdeal === idealOpen) {
      if (wantIdeal) refreshAdvice(true);
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
        await refreshAdvice(true);
      }
      syncHandAfterSidebar();
    } finally {
      sidebarBusy = false;
    }
  }

  async function refreshAdvice(force = false) {
    if (!root?.classList.contains("ideal-open")) return;
    const { game } = gameStore.getSnapshot();
    if (!game || game.mode !== "human") return;

    const key = gameRevision(game);
    if (!force && key === adviceCacheKey) return;

    const gen = ++adviceFetchGen;
    renderIdealMove(root, null, { loading: true });
    try {
      const advice = await getAdvice(game.id);
      if (gen !== adviceFetchGen || !root) return;
      adviceCacheKey = key;
      renderIdealMove(root, advice);
    } catch (err) {
      if (gen !== adviceFetchGen || !root) return;
      renderIdealMove(root, {
        available: false,
        reason: err.message || "Advice failed.",
      });
    }
  }

  function gameRevision(game) {
    if (!game) return null;
    const info = game.public_info;
    return [
      game.id,
      game.phase,
      game.status,
      game.whose_turn,
      game.trick_number,
      game.last_event || "",
      game.trick?.cards?.map((c) => `${c.player}:${c.card}`).join(",") || "",
      game.your_hand?.join(",") || "",
      game.legal_moves?.join(",") || "",
      game.pending ? JSON.stringify(game.pending) : "",
      game.finished ? "1" : "0",
      ...(game.seats || []).map((s) => `${s.hand_size}:${s.active}:${s.place || ""}`),
      info
        ? `${(info.discarded || []).join(",")}|${JSON.stringify(info.voids || {})}|${JSON.stringify(info.known_holdings || {})}`
        : "",
    ].join("|");
  }

  function renderKey(snap) {
    return `${gameRevision(snap.game)}|sort:${snap.sortMode}`;
  }

  async function doStep(opts = {}) {
    const { game } = gameStore.getSnapshot();
    if (!game || game.finished) return;
    try {
      const next = await stepGame(game.id);
      gameStore.setGame(next, { clearSelection: true });
      if (next.finished) {
        gameStore.setAutoEnabled(false);
        pacer.stop();
      }
    } catch (err) {
      gameStore.setAutoEnabled(false);
      pacer.stop();
      if (!opts.quiet) alert(err.message);
      else throw err;
    }
  }

  async function playSelected() {
    const { game, selectedCard } = gameStore.getSnapshot();
    if (!selectedCard || !game) return;
    const playBtn = root.querySelector('[data-role="play-btn"]');
    playBtn.disabled = true;
    try {
      const next = await playCard(game.id, selectedCard);
      gameStore.setGame(next, { clearSelection: true });
      pacer.schedule();
    } catch (err) {
      alert(err.message);
      updateControlsBar(root, { pacing: pacer.isPacing() });
    }
  }

  async function onConsent(accept) {
    const { game } = gameStore.getSnapshot();
    if (!game?.pending) return;
    const kind = game.pending.type;
    if (kind !== "take" && kind !== "give") return;
    try {
      const next = await answerConsent(game.id, kind, accept);
      gameStore.setGame(next, { clearSelection: true });
      pacer.schedule();
    } catch (err) {
      alert(err.message);
    }
  }

  function toggleAuto() {
    const { autoEnabled } = gameStore.getSnapshot();
    if (autoEnabled) {
      gameStore.setAutoEnabled(false);
      pacer.stop();
      return;
    }
    gameStore.setAutoEnabled(true);
    pacer.schedule();
  }

  function goLobby() {
    pacer.stop();
    gameStore.clearSession();
    navigate("/lobby");
  }

  function applyAiBannerOverrides(eventBanner, game, autoEnabled) {
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

  function sizeCenterForPlayers(n) {
    const center = root.querySelector(".center-zone");
    const trickCards = root.querySelector('[data-role="trick-cards"]');
    if (!center || !trickCards) return;
    // Reserve a slot per seat so the pot never grows/shrinks mid-game.
    const slots = Math.max(3, Math.min(8, n || 4));
    center.style.setProperty("--pot-slots", String(slots));
    // Small card 46 + gap 8; keep one row for up to 8.
    const rowW = slots * 46 + Math.max(0, slots - 1) * 8 + 24;
    center.style.width = `${Math.min(Math.max(rowW, 280), 520)}px`;
    trickCards.style.minHeight = "78px";
    trickCards.style.height = "78px";
  }

  function renderSelectionOnly() {
    if (!root) return;
    const { game, autoEnabled } = gameStore.getSnapshot();
    updateHandSelection(root.querySelector('[data-role="hand"]'));
    updateControlsBar(root, { pacing: pacer.isPacing() });
    if (game) {
      const eventBanner = root.querySelector('[data-role="event-banner"]');
      if (eventBanner) applyAiBannerOverrides(eventBanner, game, autoEnabled);
    }
  }

  function render() {
    if (!root || rendering) return;
    const snap = gameStore.getSnapshot();
    const { game, autoEnabled } = snap;
    if (!game) return;

    const key = renderKey(snap);
    // Selection / auto toggle alone should not rebuild the arena or pot.
    if (key === lastRenderKey) {
      renderSelectionOnly();
      return;
    }

    rendering = true;
    try {
      updateTopBar(game);

      const { prevTrickLen: nextLen, eventBanner } = renderTrickPot(
        root,
        game,
        prevTrickLen
      );
      applyAiBannerOverrides(eventBanner, game, autoEnabled);
      prevTrickLen = nextLen;

      const n = game.seats.length;
      const humanMode = game.mode === "human";
      const slots = seatSlots(n, humanMode);
      const arena = root.querySelector('[data-role="arena"]');

      root.classList.toggle("human-mode", humanMode);
      root.classList.toggle("ai-mode", !humanMode);
      arena.classList.toggle("human-table", humanMode);
      arena.classList.toggle("ai-table", !humanMode);
      arena.dataset.players = String(n);
      sizeCenterForPlayers(n);

      const turnOpts = {
        turnLabel:
          game.phase === "trick_reveal" &&
          (game.last_event || "").toUpperCase().includes("THULLA")
            ? "THULLA"
            : "TURN",
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
          const cur = gameStore.getSnapshot().selectedCard;
          gameStore.setSelectedCard(cur === code ? null : code);
        },
      });
      // Re-apply selection after rebuild (selectedCard not in gameRevision).
      updateHandSelection(root.querySelector('[data-role="hand"]'));
      syncSortChips(root);
      updateControlsBar(root, { pacing: pacer.isPacing() });
      renderConsentModal(root.querySelector('[data-role="take-modal"]'), game);
      renderFinishModal(root.querySelector('[data-role="finish-modal"]'), game);
      renderScratchPad(root, game);
      setIdealVisible(root, humanMode);
      if (humanMode && root.classList.contains("ideal-open")) {
        refreshAdvice(false);
      }

      lastRenderKey = key;

      if (game.finished) {
        gameStore.setAutoEnabled(false);
        pacer.stop();
      }
    } finally {
      rendering = false;
    }
  }

  function bindTable(host) {
    host.innerHTML = TEMPLATE;
    root = host.querySelector('[data-page="table"]');
    prevTrickLen = 0;
    lastRenderKey = null;

    bindSortChips(root, { onChange: () => render() });
    bindControlsBar(root, {
      onPlay: () => playSelected(),
      onStep: () => doStep(),
      onToggleAuto: () => toggleAuto(),
    });
    bindConsentModal(root.querySelector('[data-role="take-modal"]'), {
      onAnswer: onConsent,
    });
    bindFinishModal(root.querySelector('[data-role="finish-modal"]'), {
      onAgain: goLobby,
    });
    bindScratchPad(root, {
      onToggle: (open) => {
        setSidebar(open ? "scratch" : null);
      },
    });
    bindIdealMove(root, {
      onToggle: (open) => {
        setSidebar(open ? "ideal" : null);
      },
    });
    setScratchOpen(root, false);
    setIdealOpen(root, false);
    const { game: bootGame } = gameStore.getSnapshot();
    setIdealVisible(root, bootGame?.mode === "human");
    renderIdealMove(root, null);

    unsub = gameStore.subscribe(() => render());
    render();

    if (bootGame?.mode === "human") {
      pacer.schedule();
    }
  }

  return {
    async mount(host, params) {
      const mountGen = (this._mountGen = (this._mountGen || 0) + 1);
      if (mounting) return;
      mounting = true;
      try {
        let { game } = gameStore.getSnapshot();
        const routeId = params?.id;

        if ((!game || (routeId && game.id !== routeId)) && routeId) {
          try {
            const restored = await getGame(routeId);
            if (mountGen !== this._mountGen) return;
            gameStore.setGame(restored, { clearSelection: true });
            gameStore.setAutoEnabled(false);
            game = restored;
          } catch {
            if (mountGen !== this._mountGen) return;
            gameStore.clearSession();
            navigate("/lobby");
            return;
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
      if (unsub) unsub();
      unsub = null;
      root = null;
      lastRenderKey = null;
      adviceCacheKey = null;
      adviceFetchGen += 1;
    },
  };
}
