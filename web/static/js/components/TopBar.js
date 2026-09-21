/**
 * Shared top chrome (lives in shell; pages update fields).
 * @param {object|null} game
 * @param {{ reviewMode?: boolean }} [opts]
 */
export function updateTopBar(game, opts = {}) {
  const hiScore = document.querySelector('[data-role="hi-score"]');
  const modeBadge = document.querySelector('[data-role="mode-badge"]');
  const trickLabel = document.querySelector('[data-role="trick-label"]');

  if (!game) {
    hiScore.textContent = "000000";
    modeBadge.textContent = "LOBBY";
    trickLabel.textContent = "—";
    return;
  }

  const reviewing = Boolean(opts.reviewMode);

  modeBadge.textContent = reviewing
    ? "REVIEW"
    : game.mode === "human"
      ? "1P vs AI"
      : "SPECTATOR";
  trickLabel.textContent =
    game.finished && !reviewing
      ? "DONE"
      : `TRICK ${String(game.trick_number || 0).padStart(2, "0")}`;
  hiScore.textContent = String((game.trick_number || 0) * 1000).padStart(6, "0");
}
