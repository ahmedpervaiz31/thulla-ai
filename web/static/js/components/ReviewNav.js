/**
 * Bottom-right prev/next turn scrubber for completed-game review.
 */

export function renderReviewNav(root, snap) {
  const nav = root.querySelector('[data-role="review-nav"]');
  if (!nav) return;

  const active = Boolean(snap.reviewMode && snap.reviewFrames?.length);
  nav.classList.toggle("hidden", !active);
  root.classList.toggle("review-mode", active);
  if (!active) return;

  const total = snap.reviewFrames.length;
  const index = Math.max(0, Math.min(snap.reviewIndex, total - 1));
  const label = nav.querySelector('[data-role="review-label"]');
  const prevBtn = nav.querySelector('[data-role="review-prev"]');
  const nextBtn = nav.querySelector('[data-role="review-next"]');

  if (label) label.textContent = `${index + 1} / ${total}`;
  if (prevBtn) prevBtn.disabled = index <= 0;
  if (nextBtn) nextBtn.disabled = index >= total - 1;
}

/**
 * @param {HTMLElement} root
 * @param {{ onPrev: () => void, onNext: () => void, onLobby?: () => void }} handlers
 * @returns {() => void} unbind
 */
export function bindReviewNav(root, handlers) {
  const nav = root.querySelector('[data-role="review-nav"]');
  if (!nav) return () => {};

  const onPrev = () => handlers.onPrev();
  const onNext = () => handlers.onNext();
  const onLobby = () => handlers.onLobby?.();
  nav.querySelector('[data-role="review-prev"]')?.addEventListener("click", onPrev);
  nav.querySelector('[data-role="review-next"]')?.addEventListener("click", onNext);
  nav.querySelector('[data-role="review-lobby"]')?.addEventListener("click", onLobby);

  function onKey(e) {
    if (!root.classList.contains("review-mode")) return;
    const tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || e.target?.isContentEditable) {
      return;
    }
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      handlers.onPrev();
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      handlers.onNext();
    }
  }
  window.addEventListener("keydown", onKey);

  return () => {
    nav.querySelector('[data-role="review-prev"]')?.removeEventListener("click", onPrev);
    nav.querySelector('[data-role="review-next"]')?.removeEventListener("click", onNext);
    nav.querySelector('[data-role="review-lobby"]')?.removeEventListener("click", onLobby);
    window.removeEventListener("keydown", onKey);
  };
}
