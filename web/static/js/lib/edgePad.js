/**
 * Shared edge-pad drag/click binding for Ideal Move and Scratch Pad.
 *
 * @param {HTMLElement} root
 * @param {{
 *   handleRole: string,
 *   openClass: string,
 *   openSign: 1|-1,
 *   onToggle?: (open: boolean) => void,
 * }} opts
 * openSign: +1 means drag in positive dx opens (ideal/left);
 *           -1 means drag in negative dx opens (scratch/right) via inverted delta.
 */
export function bindEdgePad(root, { handleRole, openClass, openSign = 1, onToggle } = {}) {
  const handle = root.querySelector(`[data-role="${handleRole}"]`);
  if (!handle) return;

  let dragStartX = null;
  let dragMoved = false;
  let dragStartOpen = false;

  handle.addEventListener("click", (ev) => {
    if (dragMoved) {
      ev.preventDefault();
      return;
    }
    const open = !root.classList.contains(openClass);
    onToggle?.(open);
  });

  const onPointerDown = (ev) => {
    if (ev.button != null && ev.button !== 0) return;
    dragStartX = ev.clientX;
    dragMoved = false;
    dragStartOpen = root.classList.contains(openClass);
    handle.setPointerCapture?.(ev.pointerId);
  };

  const onPointerMove = (ev) => {
    if (dragStartX == null) return;
    const dx = (ev.clientX - dragStartX) * openSign;
    if (Math.abs(dx) > 10) dragMoved = true;
    if (!dragStartOpen && dx > 48) {
      dragStartOpen = true;
      onToggle?.(true);
    } else if (dragStartOpen && dx < -48) {
      dragStartOpen = false;
      onToggle?.(false);
    }
  };

  const onPointerUp = () => {
    dragStartX = null;
  };

  handle.addEventListener("pointerdown", onPointerDown);
  handle.addEventListener("pointermove", onPointerMove);
  handle.addEventListener("pointerup", onPointerUp);
  handle.addEventListener("pointercancel", onPointerUp);
}

/**
 * @param {HTMLElement} root
 * @param {string} openClass
 * @param {string} handleRole
 * @param {boolean} open
 * @param {{ openTitle: string, closeTitle: string }} titles
 */
export function setPadOpen(root, openClass, handleRole, open, titles) {
  root.classList.toggle(openClass, open);
  const handle = root.querySelector(`[data-role="${handleRole}"]`);
  if (handle) {
    handle.setAttribute("aria-expanded", open ? "true" : "false");
    handle.title = open ? titles.closeTitle : titles.openTitle;
  }
}
