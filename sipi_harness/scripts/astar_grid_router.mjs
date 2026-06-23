import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (!item.startsWith("--")) continue;
    const key = item.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

function key(x, y) {
  return `${x},${y}`;
}

function parseKey(value) {
  const [x, y] = value.split(",").map(Number);
  return { x, y };
}

function manhattan(a, b) {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

function octile(a, b) {
  const dx = Math.abs(a.x - b.x);
  const dy = Math.abs(a.y - b.y);
  return Math.max(dx, dy) + (Math.SQRT2 - 1) * Math.min(dx, dy);
}

function cellsLength(cells, gridMm) {
  let length = 0;
  for (let index = 1; index < cells.length; index += 1) {
    const prev = cells[index - 1];
    const cur = cells[index];
    const dx = Math.abs(cur.x - prev.x);
    const dy = Math.abs(cur.y - prev.y);
    length += (dx && dy ? Math.SQRT2 : 1) * gridMm;
  }
  return Number(length.toFixed(6));
}

function quantize(point, gridMm) {
  return {
    x: Math.round(point.x / gridMm),
    y: Math.round(point.y / gridMm)
  };
}

function dequantize(cell, gridMm) {
  return {
    x: Number((cell.x * gridMm).toFixed(6)),
    y: Number((cell.y * gridMm).toFixed(6))
  };
}

function rectCells(rect, gridMm) {
  const minX = Math.floor(Math.min(rect.x1, rect.x2) / gridMm);
  const maxX = Math.ceil(Math.max(rect.x1, rect.x2) / gridMm);
  const minY = Math.floor(Math.min(rect.y1, rect.y2) / gridMm);
  const maxY = Math.ceil(Math.max(rect.y1, rect.y2) / gridMm);
  const cells = [];
  for (let x = minX; x <= maxX; x += 1) {
    for (let y = minY; y <= maxY; y += 1) cells.push(key(x, y));
  }
  return cells;
}

function inflateRect(rect, clearanceMm) {
  return {
    x1: rect.x1 - clearanceMm,
    y1: rect.y1 - clearanceMm,
    x2: rect.x2 + clearanceMm,
    y2: rect.y2 + clearanceMm
  };
}

function boundsToGrid(bounds, gridMm) {
  return {
    minX: Math.floor(bounds.x1 / gridMm),
    minY: Math.floor(bounds.y1 / gridMm),
    maxX: Math.ceil(bounds.x2 / gridMm),
    maxY: Math.ceil(bounds.y2 / gridMm)
  };
}

function minByScore(open, fScore) {
  let best = null;
  let bestScore = Infinity;
  for (const item of open) {
    const score = fScore.get(item) ?? Infinity;
    if (score < bestScore) {
      best = item;
      bestScore = score;
    }
  }
  return best;
}

function reconstruct(cameFrom, currentKey) {
  const total = [parseKey(currentKey)];
  while (cameFrom.has(currentKey)) {
    currentKey = cameFrom.get(currentKey);
    total.push(parseKey(currentKey));
  }
  return total.reverse();
}

function simplifyCells(cells) {
  if (cells.length <= 2) return cells;
  const out = [cells[0]];
  let lastDir = null;
  for (let i = 1; i < cells.length; i += 1) {
    const prev = cells[i - 1];
    const cur = cells[i];
    const dir = `${Math.sign(cur.x - prev.x)},${Math.sign(cur.y - prev.y)}`;
    if (lastDir && dir !== lastDir) out.push(prev);
    lastDir = dir;
  }
  out.push(cells[cells.length - 1]);
  return out;
}

export function routeAStar(request) {
  const gridMm = request.grid_mm ?? 0.05;
  const traceWidthMm = request.trace_width_mm ?? 0.1;
  const clearanceMm = request.clearance_mm ?? 0.1;
  const lengthWeight = request.length_weight ?? 1;
  const bendPenalty = request.bend_penalty_mm != null
    ? request.bend_penalty_mm / gridMm
    : (request.bend_penalty ?? 0.15);
  const allowDiagonal = request.allow_diagonal ?? true;
  const bounds = boundsToGrid(request.bounds, gridMm);
  const start = quantize(request.start, gridMm);
  const goal = quantize(request.goal, gridMm);
  const startKey = key(start.x, start.y);
  const goalKey = key(goal.x, goal.y);
  const blocked = new Set();

  for (const obstacle of request.obstacles || []) {
    const inflated = inflateRect(obstacle, clearanceMm + traceWidthMm / 2);
    for (const cell of rectCells(inflated, gridMm)) blocked.add(cell);
  }
  blocked.delete(startKey);
  blocked.delete(goalKey);

  const open = new Set([startKey]);
  const cameFrom = new Map();
  const gScore = new Map([[startKey, 0]]);
  const heuristic = allowDiagonal ? octile : manhattan;
  const fScore = new Map([[startKey, heuristic(start, goal)]]);
  const previousDir = new Map();
  const directions = [
    { x: 1, y: 0 },
    { x: -1, y: 0 },
    { x: 0, y: 1 },
    { x: 0, y: -1 },
    ...(allowDiagonal
      ? [
          { x: 1, y: 1 },
          { x: 1, y: -1 },
          { x: -1, y: 1 },
          { x: -1, y: -1 }
        ]
      : [])
  ];
  let explored = 0;
  const maxIterations = request.max_iterations ?? 500000;

  while (open.size) {
    if (explored > maxIterations) throw new Error(`A* exceeded max_iterations=${maxIterations}`);
    explored += 1;
    const currentKey = minByScore(open, fScore);
    if (currentKey === goalKey) {
      const cells = reconstruct(cameFrom, currentKey);
      const waypoints = simplifyCells(cells).map((cell) => dequantize(cell, gridMm));
      return {
        ok: true,
        grid_mm: gridMm,
        trace_width_mm: traceWidthMm,
        clearance_mm: clearanceMm,
        allow_diagonal: allowDiagonal,
        routing_objective: "minimize_centerline_length_with_bend_penalty",
        length_weight: lengthWeight,
        bend_penalty_grid_units: bendPenalty,
        bend_penalty_mm: Number((bendPenalty * gridMm).toFixed(6)),
        explored,
        length_mm: cellsLength(cells, gridMm),
        waypoints
      };
    }

    open.delete(currentKey);
    const current = parseKey(currentKey);
    const currentDir = previousDir.get(currentKey);

    for (const dir of directions) {
      const next = { x: current.x + dir.x, y: current.y + dir.y };
      if (next.x < bounds.minX || next.x > bounds.maxX || next.y < bounds.minY || next.y > bounds.maxY) continue;
      const nextKey = key(next.x, next.y);
      if (blocked.has(nextKey)) continue;
      if (dir.x !== 0 && dir.y !== 0) {
        if (blocked.has(key(current.x + dir.x, current.y)) || blocked.has(key(current.x, current.y + dir.y))) {
          continue;
        }
      }
      const dirKey = key(dir.x, dir.y);
      const turnCost = currentDir && currentDir !== dirKey ? bendPenalty : 0;
      const stepCost = dir.x !== 0 && dir.y !== 0 ? Math.SQRT2 : 1;
      const tentative = (gScore.get(currentKey) ?? Infinity) + stepCost * lengthWeight + turnCost;
      if (tentative >= (gScore.get(nextKey) ?? Infinity)) continue;
      cameFrom.set(nextKey, currentKey);
      previousDir.set(nextKey, dirKey);
      gScore.set(nextKey, tentative);
      fScore.set(nextKey, tentative + heuristic(next, goal));
      open.add(nextKey);
    }
  }

  return { ok: false, reason: "no_path", explored };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.input || !args.output) {
    console.error("Usage: node scripts/astar_grid_router.mjs --input route_request.json --output route_result.json");
    process.exit(2);
  }
  const request = JSON.parse(fs.readFileSync(path.resolve(args.input), "utf8").replace(/^\uFEFF/, ""));
  const result = routeAStar(request);
  fs.mkdirSync(path.dirname(path.resolve(args.output)), { recursive: true });
  fs.writeFileSync(path.resolve(args.output), `${JSON.stringify(result, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(result, null, 2));
  if (!result.ok) process.exit(1);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
