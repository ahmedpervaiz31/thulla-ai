/**
 * Shared top chrome (lives in shell; pages update fields).
 */
export function updateTopBar(game) {
  const hiScore = document.querySelector('[data-role="hi-score"]');
  const modeBadge = document.querySelector('[data-role="mode-badge"]');
  const trickLabel = document.querySelector('[data-role="trick-label"]');

  if (!game) {
    hiScore.textContent = "000000";
    modeBadge.textContent = "LOBBY";
    trickLabel.textContent = "—";
    return;
  }

  modeBadge.textContent = game.mode === "human" ? "1P vs AI" : "SPECTATOR";
  trickLabel.textContent = game.finished
    ? "DONE"
    : `TRICK ${String(game.trick_number).padStart(2, "0")}`;
  hiScore.textContent = String(game.trick_number * 1000).padStart(6, "0");
}
