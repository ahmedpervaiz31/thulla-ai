/** Thin fetch wrappers for the Thulla game JSON API. */

async function post(path, body = {}) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

/**
 * @param {{ mode: "human"|"ai", players: number }} opts
 */
export function createGame({ mode, players }) {
  return post("/api/games", { mode, players });
}

export function getGame(gameId) {
  return fetch(`/api/games/${gameId}`).then(async (res) => {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    return data;
  });
}

export function playCard(gameId, card) {
  return post(`/api/games/${gameId}/play`, { card });
}

export function answerTake(gameId, accept) {
  return post(`/api/games/${gameId}/take`, { accept });
}

export function answerGive(gameId, accept) {
  return post(`/api/games/${gameId}/give`, { accept });
}

export function stepGame(gameId) {
  return post(`/api/games/${gameId}/step`, {});
}

/** Bot-policy advice for the human seat (human mode). */
export function getAdvice(gameId) {
  return fetch(`/api/games/${gameId}/advise`).then(async (res) => {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    return data;
  });
}

/** Consent for take or give pending. */
export function answerConsent(gameId, kind, accept) {
  if (kind === "take") return answerTake(gameId, accept);
  if (kind === "give") return answerGive(gameId, accept);
  return Promise.reject(new Error(`unknown consent kind: ${kind}`));
}
