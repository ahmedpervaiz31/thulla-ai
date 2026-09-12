/**
 * Game-over modal with winners + loser.
 */
export function renderFinishModal(modalRoot, game) {
  if (!game?.finished) {
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

export function bindFinishModal(modalRoot, { onAgain }) {
  modalRoot
    .querySelector('[data-role="again-btn"]')
    .addEventListener("click", onAgain);
}
