import { createLobbyPage } from "./pages/LobbyPage.js";
import { createTablePage } from "./pages/TablePage.js";
import { createRouter } from "./router.js";

/**
 * Bootstrap: hash router + page factories.
 * Shared CRT chrome (topbar / bottombar) lives in index.html.
 */
function boot() {
  const root = document.getElementById("page-root");
  const app = document.getElementById("app");
  if (!root) {
    console.error("Missing #page-root");
    return;
  }

  const router = createRouter({
    root,
    routes: {
      lobby: createLobbyPage,
      table: createTablePage,
    },
    onNavigate(match) {
      app?.classList.toggle("on-table", match.name === "table");
    },
  });

  router.start();
}

boot();
