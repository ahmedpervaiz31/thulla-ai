/**
 * Hash router: #/lobby | #/table/:id
 * Shared chrome stays in the shell; pages mount into #page-root.
 */

export function createRouter({ root, routes, onNavigate }) {
  let current = null;
  let currentPath = null;

  function parseHash() {
    const raw = (location.hash || "#/lobby").replace(/^#/, "") || "/lobby";
    const path = raw.startsWith("/") ? raw : `/${raw}`;
    const parts = path.split("/").filter(Boolean);

    if (parts[0] === "table" && parts[1]) {
      return { name: "table", path: `/table/${parts[1]}`, params: { id: parts[1] } };
    }
    if (parts[0] === "table") {
      return { name: "table", path: "/table", params: {} };
    }
    return { name: "lobby", path: "/lobby", params: {} };
  }

  function navigate(path) {
    const next = path.startsWith("#") ? path : `#${path.startsWith("/") ? path : `/${path}`}`;
    if (location.hash === next) {
      // Force remount if same hash (e.g. lobby → lobby).
      render();
      return;
    }
    location.hash = next;
  }

  function render() {
    const match = parseHash();
    const factory = routes[match.name];
    if (!factory) {
      navigate("/lobby");
      return;
    }

    if (current && currentPath === match.path) {
      return;
    }

    if (current?.unmount) current.unmount();
    current = null;
    currentPath = match.path;
    root.innerHTML = "";

    current = factory({ navigate });
    current.mount(root, match.params);
    if (onNavigate) onNavigate(match);
  }

  function start() {
    window.addEventListener("hashchange", render);
    if (!location.hash) {
      location.hash = "#/lobby";
    } else {
      render();
    }
  }

  function stop() {
    window.removeEventListener("hashchange", render);
    if (current?.unmount) current.unmount();
    current = null;
    currentPath = null;
  }

  return { start, stop, navigate, render };
}
