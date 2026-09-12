/** Tiny DOM helpers. */

export function $(id) {
  return document.getElementById(id);
}

export function $$(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

export function clearEl(el) {
  if (el) el.innerHTML = "";
}
