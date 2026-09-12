/**
 * Take / give consent modal.
 */
export function renderConsentModal(modalRoot, game) {
  const humanConsent =
    (game.pending?.type === "take" || game.pending?.type === "give") &&
    game.seats[game.pending.seat]?.is_human;

  if (!humanConsent) {
    modalRoot.classList.add("hidden");
    return;
  }

  modalRoot.classList.remove("hidden");
  const text = modalRoot.querySelector('[data-role="take-text"]');
  const yes = modalRoot.querySelector('[data-role="take-yes"]');
  const no = modalRoot.querySelector('[data-role="take-no"]');

  if (game.pending.type === "give") {
    text.textContent = `${game.pending.asker_name} asks for your ${game.pending.n_cards} cards. Give them?`;
    yes.textContent = "YES — GIVE";
    no.textContent = "NO — REFUSE";
  } else {
    text.textContent = `Ask for ${game.pending.target_name}'s ${game.pending.n_cards} cards?`;
    yes.textContent = "YES — ASK";
    no.textContent = "NO — PASS";
  }
}

export function bindConsentModal(modalRoot, { onAnswer }) {
  modalRoot
    .querySelector('[data-role="take-yes"]')
    .addEventListener("click", () => onAnswer(true));
  modalRoot
    .querySelector('[data-role="take-no"]')
    .addEventListener("click", () => onAnswer(false));
}
