/**
 * Get relationship type relative to a given entity.
 * relType is from the source's perspective:
 *   "vendor"  → source BUYS FROM target (target is source's vendor)
 *   "client"  → source SELLS TO target (target is source's client)
 * When entityId is the target, we flip.
 */
export const getRelType = (rel, entityId) => {
  if (rel.relType) {
    return rel.source === entityId ? rel.relType : (rel.relType === 'vendor' ? 'client' : 'vendor');
  }
  // Fallback when relType is missing
  return rel.source === entityId ? 'vendor' : 'client';
};

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
