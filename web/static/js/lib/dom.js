/** Tiny DOM helpers. */

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

export function clearEl(elNode) {
  if (elNode) elNode.innerHTML = "";
}
