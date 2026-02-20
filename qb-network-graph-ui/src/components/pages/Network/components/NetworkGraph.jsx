import { useState, useMemo } from 'react';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { fmt } from '@/utils/format';
import { getRelType } from '@/utils/graph';
import { applyNativeMerges } from '@/utils/perspective';
import { ENTITIES, RELATIONSHIPS } from '@/api/mock/data';

export function NetworkGraph({ selectedId, onSelect, depth, pathNodes, pathMode, onPathSelect, edgeFilter, showDormant, privacy, nativeOverrides = {}, nativeMerges = [] }) {
  const [hNode, setHNode] = useState(null);
  const [hEdge, setHEdge] = useState(null);

  const HOP_COLORS = [QB.green, QB.purple, QB.orange, QB.link];

  const hopMap = useMemo(() => {
    const map = new Map([['e1', 0]]);
    const queue = ['e1'];
    while (queue.length) {
      const id = queue.shift();
      const d = map.get(id);
      RELATIONSHIPS.forEach((r) => {
        const neighbor = r.source === id ? r.target : r.target === id ? r.source : null;
        if (neighbor && !map.has(neighbor)) {
          map.set(neighbor, d + 1);
          queue.push(neighbor);
        }
      });
    }
    return map;
  }, []);

  const directIds = useMemo(() => {
    const ids = new Set(['e1']);
    RELATIONSHIPS.forEach((r) => {
      if (r.source === 'e1') ids.add(r.target);
      if (r.target === 'e1') ids.add(r.source);
    });
    return ids;
  }, []);

  // Apply native merges to entities and relationships
  const { entities: mergedEntities, relationships: mergedRelationships } = useMemo(
    () => applyNativeMerges(ENTITIES, RELATIONSHIPS, nativeMerges),
    [nativeMerges]
  );

  // Track which entity IDs have native overrides
  const nativeOverrideIds = useMemo(() => new Set(Object.keys(nativeOverrides)), [nativeOverrides]);

  const visEnt = useMemo(() => {
    if (depth === 1) return mergedEntities.filter((e) => directIds.has(e.id));
    return mergedEntities;
  }, [depth, directIds, mergedEntities]);

  const visRel = useMemo(() => {
    const ids = new Set(visEnt.map((e) => e.id));
    return mergedRelationships.filter((r) => {
      if (!ids.has(r.source) || !ids.has(r.target)) return false;
      if (!showDormant && r.status === 'dormant') return false;
      if (edgeFilter === 'vendor' && !(r.source === 'e1')) return false;
      if (edgeFilter === 'client' && !(r.target === 'e1')) return false;
      return true;
    });
  }, [visEnt, mergedRelationships, edgeFilter, showDormant]);

  const pathEdges = useMemo(() => {
    if (!pathNodes || pathNodes.length < 2) return new Set();
    const edges = new Set();
    for (let i = 0; i < pathNodes.length - 1; i++) {
      edges.add(pathNodes[i] + '-' + pathNodes[i + 1]);
      edges.add(pathNodes[i + 1] + '-' + pathNodes[i]);
    }
    return edges;
  }, [pathNodes]);

  const node = (id) => mergedEntities.find((e) => e.id === id);
  const mx = Math.max(...mergedRelationships.map((r) => r.volume));

  return (
    <div className="graph-container">
      <svg viewBox="0 0 800 560" className="w-full h-full">
        <defs>
          {HOP_COLORS.map((color, i) => (
            <marker key={i} id={`arrow-hop-${i}`} markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L8,3 L0,6" fill={color} opacity="0.7" />
            </marker>
          ))}
          <marker id="arrow-dormant" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L8,3 L0,6" fill={QB.dormant} opacity="0.5" />
          </marker>
          <marker id="arrow-path" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L10,3.5 L0,7" fill={QB.orange} />
          </marker>
          <marker id="arrow-native" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L8,3 L0,6" fill={QB.purple} opacity="0.7" />
          </marker>
        </defs>
        <rect width="800" height="560" fill="#FAFBFC" />
        {Array.from({ length: 20 }, (_, i) =>
          Array.from({ length: 14 }, (_, j) => (
            <circle key={i + '-' + j} cx={40 * i + 20} cy={40 * j + 20} r="0.5" fill="#DDE1E6" />
          ))
        )}

        {/* Edges */}
        {visRel.map((rel, i) => {
          const s = node(rel.source), t = node(rel.target);
          if (!s || !t) return null;
          const w = Math.max(1.5, (rel.volume / mx) * 5);
          const isConn = hNode && (rel.source === hNode || rel.target === hNode);
          const isDormant = rel.status === 'dormant';
          const isOnPath = pathEdges.has(rel.source + '-' + rel.target);
          const isRemapped = rel._mergeRemapped;
          const op = isOnPath ? 1 : hNode ? (isConn ? 0.8 : 0.08) : (pathNodes && pathNodes.length > 0 ? 0.06 : (isDormant ? 0.15 : isRemapped ? 0.5 : 0.35));

          const sR = s.id === 'e1' ? 28 : 18 + Math.log(s.vendors + s.clients) * 2;
          const tR = t.id === 'e1' ? 28 : 18 + Math.log(t.vendors + t.clients) * 2;
          const dx = t.x - s.x, dy = t.y - s.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const ux = dx / dist, uy = dy / dist;
          const x1 = s.x + ux * (sR + 2), y1 = s.y + uy * (sR + 2);
          const x2 = t.x - ux * (tR + 4), y2 = t.y - uy * (tR + 4);

          const edgeHop = hopMap.get(rel.source) ?? 0;
          const edgeHopIdx = Math.min(edgeHop, HOP_COLORS.length - 1);
          const edgeColor = isOnPath ? QB.orange : isRemapped ? QB.purple : isDormant ? QB.dormant : HOP_COLORS[edgeHopIdx];
          const markerEnd = isOnPath ? 'url(#arrow-path)' : isRemapped ? 'url(#arrow-native)' : isDormant ? 'url(#arrow-dormant)' : `url(#arrow-hop-${edgeHopIdx})`;
          const dashArray = isDormant && !isOnPath ? '6 4' : isRemapped ? '3 2' : 'none';

          return (
            <g key={'e' + i}>
              <line x1={x1} y1={y1} x2={x2} y2={y2}
                stroke={edgeColor} strokeWidth={isOnPath ? w + 2 : hEdge === i ? w + 2 : w}
                strokeOpacity={hEdge === i ? 1 : op}
                strokeDasharray={dashArray}
                markerEnd={markerEnd}
                className="transition-all duration-300 cursor-pointer"
                onMouseEnter={() => setHEdge(i)} onMouseLeave={() => setHEdge(null)} />
              {hEdge === i && (
                <g>
                  <rect x={(s.x + t.x) / 2 - 55} y={(s.y + t.y) / 2 - 14} width={isRemapped ? 120 : 100} height="26" rx="4" fill="white" stroke="#D0D5DD" />
                  <text x={(s.x + t.x) / 2} y={(s.y + t.y) / 2 + 3} textAnchor="middle" fill={QB.textPrimary} fontSize="10" fontFamily="system-ui">
                    {isRemapped ? '\u24DD ' : ''}{getRelType(rel, 'e1') === 'vendor' ? '\u2190 Vendor' : '\u2192 Client'} &middot; {fmt(rel.volume)}/yr
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {visEnt.map((ent) => {
          const ind = getIndustry(ent.industry);
          const sel = selectedId === ent.id;
          const ctr = ent.id === 'e1';
          const r = ctr ? 26 : 16 + Math.log(ent.vendors + ent.clients) * 2;
          const dim = hNode && hNode !== ent.id && !visRel.some((rel) => (rel.source === hNode && rel.target === ent.id) || (rel.target === hNode && rel.source === ent.id));
          const onPath = pathNodes && pathNodes.includes(ent.id);
          const isPathEnd = pathMode && pathNodes && (pathNodes[0] === ent.id || pathNodes[pathNodes.length - 1] === ent.id);
          const isPrivate = privacy && !directIds.has(ent.id);
          const hopDist = hopMap.get(ent.id) ?? 0;
          const hopColor = HOP_COLORS[Math.min(hopDist, HOP_COLORS.length - 1)];
          const hasNative = nativeOverrideIds.has(ent.id);

          return (
            <g key={ent.id}
              onClick={() => pathMode ? onPathSelect(ent.id) : onSelect(ent)}
              onMouseEnter={() => setHNode(ent.id)} onMouseLeave={() => setHNode(null)}
              className="cursor-pointer"
              opacity={isPrivate ? 0.15 : dim ? 0.12 : (pathNodes && pathNodes.length > 0 && !onPath ? 0.12 : 1)}
              style={{ transition: 'opacity 0.3s' }}>
              {sel && !pathMode && <circle cx={ent.x} cy={ent.y} r={r + 6} fill="none" stroke={hopColor} strokeWidth="2" strokeDasharray="4 3" opacity="0.4" />}
              {isPathEnd && <circle cx={ent.x} cy={ent.y} r={r + 6} fill="none" stroke={QB.orange} strokeWidth="2.5" opacity="0.6" />}
              {onPath && !isPathEnd && <circle cx={ent.x} cy={ent.y} r={r + 4} fill={QB.orange + '15'} stroke={QB.orange} strokeWidth="1.5" opacity="0.5" />}
              <circle cx={ent.x} cy={ent.y} r={r}
                fill={isPathEnd ? QB.orange + '20' : hopColor + '18'}
                stroke={isPathEnd ? QB.orange : sel ? hopColor : hopColor + '80'}
                strokeWidth={isPathEnd ? 2.5 : sel ? 2.5 : 1.2} />
              {ctr && <text x={ent.x} y={ent.y + 4} textAnchor="middle" fill={QB.green} fontSize="12" fontWeight="bold">{'\u2605'}</text>}
              {/* Native override indicator — small purple dot at top-right of node */}
              {hasNative && !isPrivate && (
                <g>
                  <circle cx={ent.x + r * 0.65} cy={ent.y - r * 0.65} r="5" fill="white" />
                  <circle cx={ent.x + r * 0.65} cy={ent.y - r * 0.65} r="4" fill={QB.purple} />
                  <text x={ent.x + r * 0.65} y={ent.y - r * 0.65 + 3} textAnchor="middle" fill="white" fontSize="6" fontWeight="bold" fontFamily="system-ui">n</text>
                </g>
              )}
              <text x={ent.x} y={ent.y - r - 7} textAnchor="middle" fill={isPrivate ? QB.textMuted : QB.textPrimary} fontSize={ctr ? '11' : '10'} fontWeight={ctr ? '600' : '400'} fontFamily="system-ui">
                {isPrivate ? '\u2022\u2022\u2022\u2022\u2022' : ent.name.length > 20 ? ent.name.slice(0, 18) + '\u2026' : ent.name}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="graph-legend">
        <span className="flex items-center gap-1">
          <svg width="12" height="12"><circle cx="6" cy="6" r="5" fill={QB.green + '18'} stroke={QB.green} strokeWidth="1.5" /></svg>
          Center
        </span>
        <span className="flex items-center gap-1">
          <svg width="12" height="12"><circle cx="6" cy="6" r="5" fill={QB.purple + '18'} stroke={QB.purple} strokeWidth="1.5" /></svg>
          1-hop
        </span>
        <span className="flex items-center gap-1">
          <svg width="12" height="12"><circle cx="6" cy="6" r="5" fill={QB.orange + '18'} stroke={QB.orange} strokeWidth="1.5" /></svg>
          2-hop
        </span>
        <span className="flex items-center gap-1">
          <svg width="20" height="8"><line x1="0" y1="4" x2="14" y2="4" stroke={QB.purple} strokeWidth="2" /><polygon points="14,1 20,4 14,7" fill={QB.purple} /></svg>
          1-hop edge
        </span>
        <span className="flex items-center gap-1">
          <svg width="20" height="8"><line x1="0" y1="4" x2="14" y2="4" stroke={QB.orange} strokeWidth="2" /><polygon points="14,1 20,4 14,7" fill={QB.orange} /></svg>
          2-hop edge
        </span>
        <span className="flex items-center gap-1">
          <svg width="20" height="8"><line x1="0" y1="4" x2="20" y2="4" stroke={QB.dormant} strokeWidth="2" strokeDasharray="4 3" /></svg>
          Dormant
        </span>
        {nativeOverrideIds.size > 0 && (
          <span className="flex items-center gap-1">
            <svg width="12" height="12">
              <circle cx="6" cy="6" r="5" fill={QB.purple + '18'} stroke={QB.purple + '80'} strokeWidth="1" />
              <circle cx="9" cy="3" r="3" fill={QB.purple} />
              <text x="9" y="5" textAnchor="middle" fill="white" fontSize="4" fontWeight="bold">n</text>
            </svg>
            Native
          </span>
        )}
        {pathNodes && pathNodes.length > 0 && (
          <span className="flex items-center gap-1">
            <svg width="20" height="8"><line x1="0" y1="4" x2="14" y2="4" stroke={QB.orange} strokeWidth="2.5" /><polygon points="14,1 20,4 14,7" fill={QB.orange} /></svg>
            Path
          </span>
        )}
      </div>
    </div>
  );
}
