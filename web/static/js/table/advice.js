import { getAdvice } from "../api/games.js";
import { renderIdealMove } from "../components/IdealMove.js";
import { gameStore } from "../state/gameStore.js";

/** Fat game key for advice cache / render skip. */
export function gameRevision(game) {
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

/**
 * Ideal Move fetch + cache (human mode only).
 * @param {{ getRoot: () => HTMLElement|null }} ctx
 */
export function createAdviceController(ctx) {
  let adviceCacheKey = null;
  let adviceFetchGen = 0;

  async function refreshAdvice(force = false) {
    const root = ctx.getRoot();
    if (!root?.classList.contains("ideal-open")) return;
    const { game } = gameStore.getSnapshot();
    if (!game || game.mode !== "human") return;

    const key = gameRevision(game);
    if (!force && key === adviceCacheKey) return;

    const gen = ++adviceFetchGen;
    renderIdealMove(root, null, { loading: true });
    try {
      const advice = await getAdvice(game.id);
      if (gen !== adviceFetchGen || !ctx.getRoot()) return;
      adviceCacheKey = key;
      renderIdealMove(root, advice);
    } catch (err) {
      if (gen !== adviceFetchGen || !ctx.getRoot()) return;
      renderIdealMove(root, {
        available: false,
        reason: err.message || "Advice failed.",
      });
    }
  }

  function invalidate() {
    adviceCacheKey = null;
    adviceFetchGen += 1;
  }

  return { refreshAdvice, invalidate };
}
