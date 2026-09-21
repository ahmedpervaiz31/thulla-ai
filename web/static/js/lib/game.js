/** Game-state helpers shared across table UI. */

/** True when the client is in a thulla trick reveal (banner / pacing / labels). */
export function isThullaReveal(game) {
  if (!game || game.phase !== "trick_reveal") return false;
  return (game.last_event || "").toUpperCase().includes("THULLA");
}
