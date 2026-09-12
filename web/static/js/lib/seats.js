/**
 * Seat layout around the arena for 3–8 players.
 * Clockwise: after the bottom/human anchor, next seat is lower-left first.
 */

/** How many seats on each side (clockwise from bottom/anchor). */
export function layoutCounts(n, humanMode) {
  if (humanMode) {
    // Seat 0 uses the hand rail; arena is opponents only.
    const map = {
      3: { left: 1, top: 0, right: 1, bottom: 0 },
      4: { left: 1, top: 1, right: 1, bottom: 0 },
      5: { left: 2, top: 1, right: 1, bottom: 0 },
      6: { left: 2, top: 2, right: 1, bottom: 0 },
      7: { left: 2, top: 2, right: 2, bottom: 0 },
      8: { left: 3, top: 2, right: 2, bottom: 0 },
    };
    return map[n] || map[4];
  }
  const map = {
    3: { left: 1, top: 1, right: 1, bottom: 0 },
    4: { left: 1, top: 1, right: 1, bottom: 1 },
    5: { left: 2, top: 1, right: 1, bottom: 1 },
    6: { left: 2, top: 2, right: 1, bottom: 1 },
    7: { left: 2, top: 2, right: 2, bottom: 1 },
    8: { left: 2, top: 2, right: 2, bottom: 2 },
  };
  return map[n] || map[4];
}

function unwrap(arr) {
  if (!arr.length) return null;
  if (arr.length === 1) return arr[0];
  return arr;
}

/**
 * Place seats clockwise around the table.
 * After the bottom anchor, next player is nearest on the LEFT (low on the left column).
 */
export function seatSlots(n, humanMode) {
  const c = layoutCounts(n, humanMode);
  const slots = { left: [], top: [], right: [], bottom: [] };

  if (humanMode) {
    let s = 1;
    for (let i = 0; i < c.left; i++) slots.left.push(s++);
    for (let i = 0; i < c.top; i++) slots.top.push(s++);
    for (let i = 0; i < c.right; i++) slots.right.push(s++);
  } else if (c.bottom >= 1) {
    // Seat 0 at bottom; clockwise: left → top → right → extra bottom.
    slots.bottom.push(0);
    let s = 1;
    for (let i = 0; i < c.left; i++) slots.left.push(s++);
    for (let i = 0; i < c.top; i++) slots.top.push(s++);
    for (let i = 0; i < c.right; i++) slots.right.push(s++);
    while (slots.bottom.length < c.bottom && s < n) slots.bottom.push(s++);
  } else {
    // 3p AI: no bottom — start at left.
    let s = 0;
    for (let i = 0; i < c.left; i++) slots.left.push(s++);
    for (let i = 0; i < c.top; i++) slots.top.push(s++);
    for (let i = 0; i < c.right; i++) slots.right.push(s++);
  }

  return {
    left: unwrap(slots.left),
    top: unwrap(slots.top),
    right: unwrap(slots.right),
    bottom: unwrap(slots.bottom),
    counts: c,
  };
}
