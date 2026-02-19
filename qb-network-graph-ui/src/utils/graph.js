/**
 * Get relationship type relative to a given entity.
 * Edge convention: source PAYS target.
 * If entityId is source → target is their vendor.
 * If entityId is target → source is their client.
 */
export const getRelType = (rel, entityId) =>
  rel.source === entityId ? 'vendor' : 'client';

/**
 * BFS shortest path between two entity IDs.
 * Returns array of entity IDs forming the path, or null if unreachable.
 */
export function findPath(relationships, startId, endId) {
  if (startId === endId) return [startId];

  const adj = {};
  relationships.forEach((r) => {
    if (!adj[r.source]) adj[r.source] = [];
    if (!adj[r.target]) adj[r.target] = [];
    adj[r.source].push(r.target);
    adj[r.target].push(r.source);
  });

  const visited = new Set([startId]);
  const queue = [[startId, [startId]]];

  while (queue.length > 0) {
    const [current, path] = queue.shift();
    const neighbors = adj[current] || [];

    for (const neighbor of neighbors) {
      if (neighbor === endId) return [...path, neighbor];
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        queue.push([neighbor, [...path, neighbor]]);
      }
    }
  }

  return null;
}
