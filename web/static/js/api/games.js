/** Thin fetch wrappers for the Thulla game JSON API. */

async function request(method, path, body) {
  const init = { method };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

/**
 * @param {{ mode: "human"|"ai", players: number }} opts
 */
export function createGame({ mode, players }) {
  return request("POST", "/api/games", { mode, players });
}

/** @param {"completed"|"ongoing"} [bucket] */
export function listGames(bucket = "completed") {
  const q = encodeURIComponent(bucket);
  return request("GET", `/api/games?bucket=${q}`);
}

export function getGame(gameId) {
  return request("GET", `/api/games/${gameId}`);
}

export function getGameReview(gameId) {
  return request("GET", `/api/games/${gameId}/review`);
}

export function playCard(gameId, card) {
  return request("POST", `/api/games/${gameId}/play`, { card });
}

export function answerTake(gameId, accept) {
  return request("POST", `/api/games/${gameId}/take`, { accept });
}

export function answerGive(gameId, accept) {
  return request("POST", `/api/games/${gameId}/give`, { accept });
}

export function stepGame(gameId) {
  return request("POST", `/api/games/${gameId}/step`, {});
}

/** Bot-policy advice for the human seat (human mode). */
export function getAdvice(gameId) {
  return request("GET", `/api/games/${gameId}/advise`);
}

/** Consent for take or give pending. */
export function answerConsent(gameId, kind, accept) {
  if (kind === "take") return answerTake(gameId, accept);
  if (kind === "give") return answerGive(gameId, accept);
  return Promise.reject(new Error(`unknown consent kind: ${kind}`));
}
