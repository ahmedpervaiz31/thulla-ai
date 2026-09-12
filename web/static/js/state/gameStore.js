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
  };

  getSnapshot() {
    return this.#snapshot;
  }

  get game() {
    return this.#snapshot.game;
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

  /** Reset session fields when returning to lobby. */
  clearSession() {
    this.patch({
      game: null,
      selectedCard: null,
      autoEnabled: false,
    });
  }
}

export const gameStore = new GameStore();
