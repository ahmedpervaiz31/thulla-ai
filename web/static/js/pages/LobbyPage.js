import { createGame } from "../api/games.js";
import { gameStore } from "../state/gameStore.js";
import { updateTopBar } from "../components/TopBar.js";

const TEMPLATE = `
<main class="lobby" data-page="lobby">
  <h1 class="title">THULLA</h1>
  <p class="subtitle">CLASSIC SOUTH ASIAN CARD GAME</p>

  <section class="panel">
    <h2 class="panel-title">▶ SELECT GAME MODE ◀</h2>

    <div class="mode-row">
      <button type="button" class="mode-btn selected" data-mode="human" data-role="mode-human">
        <span class="mode-icon">🎮</span>
        <span class="mode-name">HUMAN VS AI</span>
        <span class="mode-sub">1 PLAYER • PRIVATE</span>
      </button>
      <button type="button" class="mode-btn" data-mode="ai" data-role="mode-ai">
        <span class="mode-icon">🤖</span>
        <span class="mode-name">AI VS AI</span>
        <span class="mode-sub">SPECTATOR • BOT SIM</span>
      </button>
    </div>

    <div class="players-block">
      <div class="players-head">
        <span>PLAYERS COUNT</span>
        <span data-role="players-hint">4 PLAYERS</span>
      </div>
      <div class="players-row" data-role="players-row">
        <button type="button" class="p-btn" data-n="3">3P</button>
        <button type="button" class="p-btn selected" data-n="4">4P</button>
        <button type="button" class="p-btn" data-n="5">5P</button>
        <button type="button" class="p-btn" data-n="6">6P</button>
        <button type="button" class="p-btn" data-n="7">7P</button>
        <button type="button" class="p-btn" data-n="8">8P</button>
      </div>
      <p class="players-note">FULL 52-CARD DECK DEALT EVENLY. AS OPENS FIRST TRICK.</p>
    </div>

    <button type="button" class="start-btn" data-role="start-btn">▶ PRESS START • DEAL CARDS</button>
  </section>
</main>
`;

/**
 * Lobby: mode + player count → create game → navigate to table.
 */
export function createLobbyPage({ navigate }) {
  let root = null;
  let unsub = null;

  function syncFromStore() {
    if (!root) return;
    const { lobbyMode, playerCount } = gameStore.getSnapshot();

    root.querySelectorAll(".mode-btn").forEach((btn) => {
      btn.classList.toggle("selected", btn.dataset.mode === lobbyMode);
    });
    root.querySelectorAll(".p-btn").forEach((btn) => {
      btn.classList.toggle("selected", Number(btn.dataset.n) === playerCount);
    });
    root.querySelector('[data-role="players-hint"]').textContent =
      `${playerCount} PLAYERS`;
  }

  async function onStart() {
    const startBtn = root.querySelector('[data-role="start-btn"]');
    const { lobbyMode, playerCount } = gameStore.getSnapshot();
    startBtn.disabled = true;
    try {
      const game = await createGame({ mode: lobbyMode, players: playerCount });
      gameStore.setGame(game, { clearSelection: true });
      gameStore.setAutoEnabled(false);
      navigate(`/table/${game.id}`);
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      startBtn.disabled = false;
    }
  }

  return {
    mount(host) {
      host.innerHTML = TEMPLATE;
      root = host.querySelector('[data-page="lobby"]');
      updateTopBar(null);

      root.querySelectorAll(".mode-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          gameStore.setLobbyMode(btn.dataset.mode);
        });
      });

      root.querySelectorAll(".p-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          gameStore.setPlayerCount(Number(btn.dataset.n));
        });
      });

      root
        .querySelector('[data-role="start-btn"]')
        .addEventListener("click", onStart);

      unsub = gameStore.subscribe(syncFromStore);
      syncFromStore();
    },

    unmount() {
      if (unsub) unsub();
      unsub = null;
      root = null;
    },
  };
}
