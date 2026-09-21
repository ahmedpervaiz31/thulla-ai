/**
 * Game-over modal with winners + loser.
 * Can dismiss into review (stay on table) or return to lobby.
 */
export function renderFinishModal(modalRoot, game, opts = {}) {
  if (!game?.finished || opts.dismissed || opts.reviewMode) {
    modalRoot.classList.add("hidden");
    return;
  }

  const list = modalRoot.querySelector('[data-role="finish-list"]');
  list.innerHTML = "";
  game.winners.forEach((w) => {
    const li = document.createElement("li");
    li.textContent = `${w.name}`;
    list.appendChild(li);
  });
  if (game.loser) {
    const li = document.createElement("li");
    li.className = "loser";
    li.textContent = `LOSER: ${game.loser}`;
    list.appendChild(li);
  }
  modalRoot.classList.remove("hidden");
}

export function bindFinishModal(modalRoot, { onAgain, onReview }) {
  modalRoot
    .querySelector('[data-role="again-btn"]')
    .addEventListener("click", onAgain);
  const reviewBtn = modalRoot.querySelector('[data-role="review-btn"]');
  if (reviewBtn && onReview) {
    reviewBtn.addEventListener("click", onReview);
  }
}
