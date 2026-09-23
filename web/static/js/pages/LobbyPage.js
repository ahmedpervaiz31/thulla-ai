import { createGame, listGames } from "../api/games.js";
import { MAX_PLAYERS, MIN_PLAYERS } from "../constants/lobby.js";
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
      <div class="players-row" data-role="players-row"></div>
      <p class="players-note">FULL 52-CARD DECK DEALT EVENLY. AS OPENS FIRST TRICK. 4 PLAYERS USE THE TRAINED DMC BOT WHEN AVAILABLE.</p>
    </div>

    <button type="button" class="start-btn" data-role="start-btn">▶ PRESS START • DEAL CARDS</button>
  </section>

  <button type="button" class="history-open-btn" data-role="history-open">
    ▶ VIEW PREVIOUS GAMES
  </button>

  <div class="history-modal hidden" data-role="history-modal" aria-hidden="true">
    <div class="history-modal-backdrop" data-role="history-close"></div>
    <div class="history-modal-panel" role="dialog" aria-labelledby="history-modal-title">
      <div class="history-modal-head">
        <h2 class="history-modal-title" id="history-modal-title">PREVIOUS GAMES</h2>
        <button type="button" class="history-close-btn" data-role="history-close" aria-label="Close">✕</button>
      </div>
      <div class="history-list" data-role="history-list">
        <p class="history-empty" data-role="history-empty">LOADING…</p>
      </div>
    </div>
  </div>
</main>
`;

/** Format like 15/09/26 15:20 */
function formatPlayedAt(savedAt) {
  if (savedAt == null || Number.isNaN(Number(savedAt))) return "??/??/?? ??:??";
  const ms = Number(savedAt) < 1e12 ? Number(savedAt) * 1000 : Number(savedAt);
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return "??/??/?? ??:??";
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yy = String(d.getFullYear()).slice(-2);
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}/${mm}/${yy} ${hh}:${min}`;
}

/**
 * Lobby: mode + player count → create game → navigate to table.
 */
export function createLobbyPage({ navigate }) {
  let root = null;
  let unsub = null;
  let gamesCache = [];

  function buildPlayerButtons() {
    const row = root.querySelector('[data-role="players-row"]');
    row.innerHTML = "";
    for (let n = MIN_PLAYERS; n <= MAX_PLAYERS; n += 1) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "p-btn";
      btn.dataset.n = String(n);
      btn.textContent = `${n}P`;
      btn.addEventListener("click", () => {
        gameStore.setPlayerCount(n);
      });
      row.appendChild(btn);
    }
  }

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

  function setHistoryOpen(open) {
    const modal = root?.querySelector('[data-role="history-modal"]');
    if (!modal) return;
    if (open) {
      modal.classList.remove("hidden");
      modal.setAttribute("aria-hidden", "false");
      // Double rAF so the browser applies the closed styles before animating open.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => modal.classList.add("is-open"));
      });
      return;
    }
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      modal.classList.add("hidden");
      modal.removeEventListener("transitionend", onEnd);
    };
    const onEnd = (e) => {
      if (e.target === modal || e.target?.classList?.contains("history-modal-panel")) {
        finish();
      }
    };
    modal.addEventListener("transitionend", onEnd);
    setTimeout(finish, 280);
  }

  function renderHistory(games) {
    const list = root.querySelector('[data-role="history-list"]');
    if (!list) return;
    list.innerHTML = "";
    if (!games.length) {
      const empty = document.createElement("p");
      empty.className = "history-empty";
      empty.textContent = "NO COMPLETED GAMES YET";
      list.appendChild(empty);
      return;
    }

    games.forEach((g) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "history-item";
      btn.disabled = !g.reviewable;
      const modeLabel = g.mode === "human" ? "HUMAN VS AI" : "AI VS AI";
      btn.innerHTML = `
        <span class="history-when">${formatPlayedAt(g.saved_at)}</span>
        <span class="history-mode">${modeLabel}</span>
      `;
      if (g.reviewable) {
        btn.addEventListener("click", () => {
          setHistoryOpen(false);
          gameStore.clearSession();
          navigate(`/review/${g.id}`);
        });
      }
      list.appendChild(btn);
    });
  }

  async function loadHistory() {
    try {
      const data = await listGames("completed");
      if (!root) return;
      gamesCache = data.games || [];
      renderHistory(gamesCache);
    } catch {
      if (!root) return;
      gamesCache = [];
      const list = root.querySelector('[data-role="history-list"]');
      if (!list) return;
      list.innerHTML = "";
      const empty = document.createElement("p");
      empty.className = "history-empty";
      empty.textContent = "COULD NOT LOAD HISTORY";
      list.appendChild(empty);
    }
  }

  async function onStart() {
    const startBtn = root.querySelector('[data-role="start-btn"]');
    const { lobbyMode, playerCount } = gameStore.getSnapshot();
    startBtn.disabled = true;
    try {
      gameStore.clearSession();
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
      buildPlayerButtons();

      root.querySelectorAll(".mode-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          gameStore.setLobbyMode(btn.dataset.mode);
        });
      });

      root
        .querySelector('[data-role="start-btn"]')
        .addEventListener("click", onStart);

      root
        .querySelector('[data-role="history-open"]')
        .addEventListener("click", async () => {
          setHistoryOpen(true);
          await loadHistory();
        });

      root.querySelectorAll('[data-role="history-close"]').forEach((el) => {
        el.addEventListener("click", () => setHistoryOpen(false));
      });

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
