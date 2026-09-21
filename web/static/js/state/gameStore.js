import {
  DEFAULT_LOBBY_MODE,
  DEFAULT_PLAYER_COUNT,
  SORT_SUIT,
} from "../constants/lobby.js";

/**
 * Central mutable UI + session snapshot.
 * Pages/components subscribe; never mutate game JSON in place from outside.
 */
class GameStore {
  #listeners = new Set();

  #snapshot = {
    lobbyMode: DEFAULT_LOBBY_MODE,
    playerCount: DEFAULT_PLAYER_COUNT,
    game: null,
    selectedCard: null,
    sortMode: SORT_SUIT,
    autoEnabled: false,
    /** When true, table shows scrubbed review frames instead of live play. */
    reviewMode: false,
    reviewFrames: null,
    reviewIndex: 0,
    /** User closed the finish modal but stayed on the table. */
    finishDismissed: false,
    /** Seat index whose hand is open in review peek modal. */
    peekSeat: null,
  };

  getSnapshot() {
    return this.#snapshot;
  }

  get game() {
    return this.#snapshot.game;
  }

  /** Live game, or the current review frame when reviewing. */
  displayGame() {
    const snap = this.#snapshot;
    if (snap.reviewMode && snap.reviewFrames?.length) {
      const i = Math.max(0, Math.min(snap.reviewIndex, snap.reviewFrames.length - 1));
      return snap.reviewFrames[i];
    }
    return snap.game;
  }

  subscribe(listener) {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  }

  #notify() {
    const snap = this.#snapshot;
    for (const fn of this.#listeners) fn(snap);
  }

  patch(partial) {
    this.#snapshot = { ...this.#snapshot, ...partial };
    this.#notify();
  }

  setLobbyMode(lobbyMode) {
    if (this.#snapshot.lobbyMode === lobbyMode) return;
    this.patch({ lobbyMode });
  }

  setPlayerCount(playerCount) {
    if (this.#snapshot.playerCount === playerCount) return;
    this.patch({ playerCount });
  }

  setSortMode(sortMode) {
    if (this.#snapshot.sortMode === sortMode) return;
    this.patch({ sortMode });
  }

  setSelectedCard(selectedCard) {
    if (this.#snapshot.selectedCard === selectedCard) return;
    this.patch({ selectedCard });
  }

  setAutoEnabled(autoEnabled) {
    if (this.#snapshot.autoEnabled === autoEnabled) return;
    this.patch({ autoEnabled });
  }

  /**
   * Replace game state from API. Clears selection by default.
   * @param {object|null} game
   * @param {{ clearSelection?: boolean }} [opts]
   */
  setGame(game, opts = {}) {
    const clearSelection = opts.clearSelection !== false;
    this.patch({
      game,
      selectedCard: clearSelection ? null : this.#snapshot.selectedCard,
    });
  }

  setFinishDismissed(finishDismissed) {
    if (this.#snapshot.finishDismissed === finishDismissed) return;
    this.patch({ finishDismissed });
  }

  setPeekSeat(peekSeat) {
    if (this.#snapshot.peekSeat === peekSeat) return;
    this.patch({ peekSeat });
  }

  /**
   * Enter turn-by-turn review. Starts at the first frame by default.
   * @param {object[]} frames
   * @param {{ index?: number }} [opts]
   */
  enterReview(frames, opts = {}) {
    const list = Array.isArray(frames) ? frames : [];
    if (!list.length) return;
    const last = list.length - 1;
    const index = opts.index != null ? opts.index : 0;
    const clamped = Math.max(0, Math.min(index, last));
    this.patch({
      reviewMode: true,
      reviewFrames: list,
      reviewIndex: clamped,
      finishDismissed: true,
      selectedCard: null,
      autoEnabled: false,
      peekSeat: null,
      game: list[clamped],
    });
  }

  setReviewIndex(index) {
    const { reviewMode, reviewFrames } = this.#snapshot;
    if (!reviewMode || !reviewFrames?.length) return;
    const next = Math.max(0, Math.min(index, reviewFrames.length - 1));
    if (next === this.#snapshot.reviewIndex) return;
    this.patch({
      reviewIndex: next,
      game: reviewFrames[next],
      selectedCard: null,
      // Keep peek seat; hand content updates with the frame.
    });
  }

  stepReview(delta) {
    this.setReviewIndex(this.#snapshot.reviewIndex + delta);
  }

  clearReview() {
    if (!this.#snapshot.reviewMode && !this.#snapshot.reviewFrames) return;
    this.patch({
      reviewMode: false,
      reviewFrames: null,
      reviewIndex: 0,
      peekSeat: null,
    });
  }

  /** Reset session fields when returning to lobby. */
  clearSession() {
    this.patch({
      game: null,
      selectedCard: null,
      autoEnabled: false,
      reviewMode: false,
      reviewFrames: null,
      reviewIndex: 0,
      finishDismissed: false,
      peekSeat: null,
    });
  }
}

export const gameStore = new GameStore();
