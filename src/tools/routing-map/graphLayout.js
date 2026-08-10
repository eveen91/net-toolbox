// Pure, framework-free graph-layout helpers for Network Visualization.
//
// Circular-layout crossing minimization is NP-hard in general, so this uses
// a pragmatic heuristic rather than an exact solver:
//   1. Seed a starting order by walking the graph breadth-first from each
//      component's highest-degree node — this alone clusters connected
//      hosts together instead of scattering them arbitrarily.
//   2. Hill-climb that seed with pairwise swaps, keeping any swap that
//      reduces the total crossing count, until a full pass finds no
//      further improvement (or the pass budget runs out).
// "Good enough, fast" matters more here than a mathematically optimal
// arrangement, and in practice these graphs are tens of hosts, not
// thousands, so an O(n^2)-per-pass search is comfortably fast enough.

// Evenly spaced points around a circle, as percentages of a 0-100 box —
// shared by both the SVG edge overlay (viewBox="0 0 100 100") and the node
// divs (left/top %), so the two always agree without pixel measurement.
export function circleLayout(count) {
  if (count <= 0) return [];
  if (count === 1) return [{ x: 50, y: 50 }];
  const cx = 50;
  const cy = 50;
  const r = 38;
  const positions = [];
  for (let i = 0; i < count; i++) {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2; // start at top
    positions.push({ x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) });
  }
  return positions;
}

// Do the straight-line chords (a,b) and (c,d) cross, where each letter is
// a position index (0..n-1) in the circular order? Chords that share an
// endpoint meet at a point rather than crossing — callers should skip
// those pairs rather than pass them in.
function chordsCross(a, b, c, d) {
  if (a > b) [a, b] = [b, a];
  const cInside = a < c && c < b;
  const dInside = a < d && d < b;
  return cInside !== dInside; // exactly one endpoint of the other chord lies between a and b
}

// Total pairwise edge crossings for a given circular `order` (array of
// host names) and `edges` (array of [hostA, hostB] pairs). Edges naming a
// host not present in `order` are ignored rather than throwing.
export function countCrossings(order, edges) {
  const indexOf = new Map(order.map((h, i) => [h, i]));
  const pts = edges
    .map(([a, b]) => [indexOf.get(a), indexOf.get(b)])
    .filter(([a, b]) => a !== undefined && b !== undefined);

  let crossings = 0;
  for (let i = 0; i < pts.length; i++) {
    const [a, b] = pts[i];
    for (let j = i + 1; j < pts.length; j++) {
      const [c, d] = pts[j];
      if (a === c || a === d || b === c || b === d) continue; // shared endpoint — meets, doesn't cross
      if (chordsCross(a, b, c, d)) crossings++;
    }
  }
  return crossings;
}

// Walks the graph breadth-first, starting each connected component from
// its highest-degree host, visiting higher-degree neighbors first. This
// keeps a hub and its neighbors clustered on one arc of the circle instead
// of scattered, which by itself removes most easily-avoidable crossings
// before any local search runs.
function bfsSeedOrder(hostNames, edges) {
  const adjacency = new Map(hostNames.map((h) => [h, new Set()]));
  for (const [a, b] of edges) {
    if (adjacency.has(a) && adjacency.has(b) && a !== b) {
      adjacency.get(a).add(b);
      adjacency.get(b).add(a);
    }
  }

  const remaining = new Set(hostNames);
  const order = [];
  while (remaining.size > 0) {
    let start = null;
    let bestDegree = -1;
    for (const h of remaining) {
      const degree = adjacency.get(h).size;
      if (degree > bestDegree) {
        bestDegree = degree;
        start = h;
      }
    }

    const queue = [start];
    remaining.delete(start);
    while (queue.length > 0) {
      const current = queue.shift();
      order.push(current);
      const neighbors = [...adjacency.get(current)]
        .filter((n) => remaining.has(n))
        .sort((a, b) => adjacency.get(b).size - adjacency.get(a).size);
      for (const n of neighbors) {
        remaining.delete(n);
        queue.push(n);
      }
    }
  }
  return order;
}

function shuffled(arr) {
  const copy = [...arr];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

// Hill-climbs `order` by trying every pairwise swap and keeping any that
// reduces the total crossing count, repeating full passes until one finds
// no improvement (or `maxPasses` is hit, or crossings hit zero).
function localSearch(order, edges, maxPasses) {
  const current = [...order];
  let currentCrossings = countCrossings(current, edges);

  for (let pass = 0; pass < maxPasses && currentCrossings > 0; pass++) {
    let improvedThisPass = false;
    for (let i = 0; i < current.length; i++) {
      for (let j = i + 1; j < current.length; j++) {
        [current[i], current[j]] = [current[j], current[i]];
        const crossings = countCrossings(current, edges);
        if (crossings < currentCrossings) {
          currentCrossings = crossings;
          improvedThisPass = true;
        } else {
          [current[i], current[j]] = [current[j], current[i]]; // revert, no improvement
        }
      }
    }
    if (!improvedThisPass) break;
  }

  return { order: current, crossings: currentCrossings };
}

// Above this many hosts, the O(n^2)-per-pass local search stops being
// "fast enough for a UI redraw" — we fall back to just the BFS seed order,
// which is still a solid improvement over an arbitrary order.
const LOCAL_SEARCH_NODE_LIMIT = 40;

// Picks a circular order for `hostNames` that heuristically minimizes edge
// crossings when laid out with circleLayout(). `edgePairs` is
// [[hostA, hostB], ...] — only endpoint names are used.
export function optimizeNodeOrder(hostNames, edgePairs) {
  if (hostNames.length <= 3 || edgePairs.length === 0) return [...hostNames];

  const seed = bfsSeedOrder(hostNames, edgePairs);
  if (hostNames.length > LOCAL_SEARCH_NODE_LIMIT) return seed;

  const restarts = hostNames.length <= 12 ? 6 : hostNames.length <= 24 ? 3 : 1;
  const maxPasses = hostNames.length <= 24 ? 20 : 8;

  let best = localSearch(seed, edgePairs, maxPasses);
  for (let r = 1; r < restarts && best.crossings > 0; r++) {
    const attempt = localSearch(shuffled(seed), edgePairs, maxPasses);
    if (attempt.crossings < best.crossings) best = attempt;
  }
  return best.order;
}
