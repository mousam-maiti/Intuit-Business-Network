import { useState, useMemo, useCallback, useRef } from 'react';
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
import { QB } from '@/constants/colors';
import { fmt } from '@/utils/format';
import { config } from '@/config/env';

const CENTER_ID = config.currentEntityId;
const CX = 500, CY = 400;

/**
 * BFS radial layout — concentric rings by hop distance from center.
 * Children cluster near their BFS parent for a natural tree-like spread.
 */
function computeRadialLayout(entities, relationships, centerId) {
  const positions = new Map();
  if (!entities.length) return { positions, depthMap: new Map() };

  // Build undirected adjacency
  const adj = new Map();
  entities.forEach(e => adj.set(e.id, []));
  relationships.forEach(r => {
    if (adj.has(r.source) && adj.has(r.target)) {
      adj.get(r.source).push(r.target);
      adj.get(r.target).push(r.source);
    }
  });

  // BFS from center
  const depthMap = new Map();
  const parentOf = new Map();
  depthMap.set(centerId, 0);
  const queue = [centerId];
  let maxDepth = 0;

  while (queue.length) {
    const id = queue.shift();
    const d = depthMap.get(id);
    for (const neighbor of (adj.get(id) || [])) {
      if (!depthMap.has(neighbor)) {
        depthMap.set(neighbor, d + 1);
        parentOf.set(neighbor, id);
        maxDepth = Math.max(maxDepth, d + 1);
        queue.push(neighbor);
      }
    }
  }

  // Group by depth
  const byDepth = new Map();
  entities.forEach(e => {
    const d = depthMap.get(e.id);
    if (d === undefined) return;
    if (!byDepth.has(d)) byDepth.set(d, []);
    byDepth.get(d).push(e);
  });

  // Place center
  positions.set(centerId, { x: CX, y: CY });

  // Depth 1: even distribution on ring
  const depth1 = byDepth.get(1) || [];
  const r1 = 200;
  const depth1Angles = new Map();
  depth1.forEach((e, i) => {
    const angle = (2 * Math.PI * i) / depth1.length - Math.PI / 2;
    depth1Angles.set(e.id, angle);
    positions.set(e.id, {
      x: CX + r1 * Math.cos(angle),
      y: CY + r1 * Math.sin(angle),
    });
  });

  // Depth 2+: fan out from parent in the parent's direction from center
  for (let d = 2; d <= maxDepth; d++) {
    const ents = byDepth.get(d) || [];
    const byParent = new Map();
    ents.forEach(e => {
      const p = parentOf.get(e.id);
      if (!byParent.has(p)) byParent.set(p, []);
      byParent.get(p).push(e);
    });

    const rOuter = r1 + (d - 1) * 150;

    byParent.forEach((children, parentId) => {
      const pp = positions.get(parentId);
      if (!pp) return;
      const parentAngle = Math.atan2(pp.y - CY, pp.x - CX);
      const fanSpread = Math.min(Math.PI * 0.35, 0.15 + children.length * 0.1);

      children.forEach((e, i) => {
        const frac = children.length > 1 ? i / (children.length - 1) - 0.5 : 0;
        const angle = parentAngle + fanSpread * frac;
        positions.set(e.id, {
          x: CX + rOuter * Math.cos(angle),
          y: CY + rOuter * Math.sin(angle),
        });
      });
    });
  }

  return { positions, depthMap };
}

// Edge color by relationship direction relative to the entity pair
const VENDOR_COLOR = QB.purple;
const CLIENT_COLOR = QB.cyan || '#0284c7';

export function NetworkGraph({ selectedId, onSelect, depth, pathNodes, pathMode, onPathSelect, edgeFilter, showDormant, nativeOverrides = {}, nativeMerges = [], allEntities = [], allRelationships = [], supplyChainNodes = null }) {
  const [hNode, setHNode] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const svgRef = useRef(null);
  const dragRef = useRef(null);

  const zoomIn = useCallback(() => setZoom(z => Math.min(z * 1.25, 4)), []);
  const zoomOut = useCallback(() => setZoom(z => Math.max(z / 1.25, 0.25)), []);
  const zoomReset = useCallback(() => { setZoom(1); setPan({ x: 0, y: 0 }); }, []);

  const handleWheel = useCallback((e) => {
    e.preventDefault();
    setZoom(z => {
      const factor = e.deltaY < 0 ? 1.08 : 1 / 1.08;
      return Math.min(Math.max(z * factor, 0.25), 4);
    });
  }, []);

  // Compute radial layout based on relationships
  const { positions, depthMap } = useMemo(
    () => computeRadialLayout(allEntities, allRelationships, CENTER_ID),
    [allEntities, allRelationships]
  );

  const nativeOverrideIds = useMemo(() => new Set(Object.keys(nativeOverrides)), [nativeOverrides]);

  // Visible relationships (filtered by vendor/client toggle)
  const visRel = useMemo(() => {
    const ids = new Set(allEntities.map(e => e.id));
    return allRelationships.filter(r => {
      if (!ids.has(r.source) || !ids.has(r.target)) return false;
      if (edgeFilter === 'vendor' && r.source !== CENTER_ID) return false;
      if (edgeFilter === 'client' && r.target !== CENTER_ID) return false;
      return true;
    });
  }, [allEntities, allRelationships, edgeFilter]);

  // Filter entities to only those with visible relationships
  const visEnt = useMemo(() => {
    if (edgeFilter === 'all') return allEntities.filter(e => e.id !== CENTER_ID);
    const visIds = new Set();
    visRel.forEach(r => { visIds.add(r.source); visIds.add(r.target); });
    visIds.delete(CENTER_ID);
    return allEntities.filter(e => visIds.has(e.id));
  }, [allEntities, visRel, edgeFilter]);

  const pos = (id) => positions.get(id) || { x: CX, y: CY };
  const mx = Math.max(...allRelationships.map(r => r.volume), 1);

  // Dynamic viewBox
  const vb = useMemo(() => {
    const allPos = [...positions.values()];
    if (!allPos.length) return { x: 0, y: 0, w: 1000, h: 800 };
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    allPos.forEach(p => {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    });
    const pad = 100;
    return {
      x: minX - pad,
      y: minY - pad,
      w: Math.max(maxX - minX + pad * 2, 400),
      h: Math.max(maxY - minY + pad * 2, 400),
    };
  }, [positions]);

  // Pan handlers (depend on vb and zoom)
  const handleMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    dragRef.current = { startX: e.clientX, startY: e.clientY, startPan: { ...pan }, dragged: false };
  }, [pan]);

  const handleMouseMove = useCallback((e) => {
    if (!dragRef.current) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    if (!dragRef.current.dragged && Math.abs(dx) + Math.abs(dy) < 4) return;
    dragRef.current.dragged = true;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const vbW = vb.w / zoom;
    const vbH = vb.h / zoom;
    const svgDx = dx * (vbW / rect.width);
    const svgDy = dy * (vbH / rect.height);
    setPan({ x: dragRef.current.startPan.x - svgDx, y: dragRef.current.startPan.y - svgDy });
  }, [zoom, vb]);

  const handleMouseUp = useCallback(() => {
    dragRef.current = null;
  }, []);

  // Hovered node's neighbors
  const hoverNeighbors = useMemo(() => {
    if (!hNode) return null;
    const set = new Set();
    allRelationships.forEach(r => {
      if (r.source === hNode) set.add(r.target);
      if (r.target === hNode) set.add(r.source);
    });
    set.add(hNode);
    return set;
  }, [hNode, allRelationships]);

  // Supply chain highlighting
  const scSet = useMemo(() => supplyChainNodes ? new Set(supplyChainNodes) : null, [supplyChainNodes]);

  // Depth ring colors
  const depthColor = (d) => {
    const colors = [QB.green, QB.purple, QB.orange, QB.cyan || '#0284c7', QB.red || '#dc2626', '#6b7280'];
    return colors[Math.min(d, colors.length - 1)];
  };

  return (
    <div className="graph-container">
      <svg ref={svgRef} onWheel={handleWheel}
        onMouseDown={handleMouseDown} onMouseMove={handleMouseMove} onMouseUp={handleMouseUp} onMouseLeave={handleMouseUp}
        viewBox={`${vb.x + vb.w * (1 - 1 / zoom) / 2 + pan.x} ${vb.y + vb.h * (1 - 1 / zoom) / 2 + pan.y} ${vb.w / zoom} ${vb.h / zoom}`}
        className="w-full h-full" style={{ background: '#FAFBFC', cursor: dragRef.current ? 'grabbing' : 'grab' }}>
        <defs>
          <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="1" stdDeviation="2" floodOpacity="0.1" />
          </filter>
          <marker id="arrow-vendor" markerWidth="6" markerHeight="4" refX="5" refY="2" orient="auto">
            <path d="M0,0 L6,2 L0,4" fill={VENDOR_COLOR} opacity="0.4" />
          </marker>
          <marker id="arrow-client" markerWidth="6" markerHeight="4" refX="5" refY="2" orient="auto">
            <path d="M0,0 L6,2 L0,4" fill={CLIENT_COLOR} opacity="0.4" />
          </marker>
          <marker id="arrow-chain" markerWidth="6" markerHeight="4" refX="5" refY="2" orient="auto">
            <path d="M0,0 L6,2 L0,4" fill={QB.green} opacity="0.5" />
          </marker>
        </defs>

        {/* Relationship edges — direct entity-to-entity */}
        {visRel.map(r => {
          const sp = pos(r.source);
          const tp = pos(r.target);
          const dx = tp.x - sp.x, dy = tp.y - sp.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const ux = dx / dist, uy = dy / dist;

          const w = Math.max(1, (r.volume / mx) * 4);
          const isVendor = r.source !== CENTER_ID && r.target === CENTER_ID;
          const color = isVendor ? VENDOR_COLOR : CLIENT_COLOR;

          const sourceInChain = scSet && scSet.has(r.source);
          const targetInChain = scSet && scSet.has(r.target);
          const edgeInChain = sourceInChain && targetInChain;

          const isHoverConnected = hoverNeighbors && (hoverNeighbors.has(r.source) && hoverNeighbors.has(r.target));
          const isDimmed = (hoverNeighbors && !isHoverConnected) || (scSet && !edgeInChain);

          const marker = edgeInChain ? 'url(#arrow-chain)' : isVendor ? 'url(#arrow-vendor)' : 'url(#arrow-client)';

          return (
            <line key={`e-${r.source}-${r.target}`}
              x1={sp.x + ux * 14} y1={sp.y + uy * 14}
              x2={tp.x - ux * 14} y2={tp.y - uy * 14}
              stroke={edgeInChain ? QB.green : color}
              strokeWidth={edgeInChain ? w + 1 : isHoverConnected ? w + 1 : w}
              strokeOpacity={isDimmed ? 0.04 : edgeInChain ? 0.55 : isHoverConnected ? 0.6 : 0.18}
              markerEnd={marker}
              className="transition-all duration-300"
            />
          );
        })}

        {/* Center node */}
        {(() => {
          const center = allEntities.find(e => e.id === CENTER_ID);
          if (!center) return null;
          return (
            <g className="cursor-pointer" onClick={() => onSelect(center)}>
              <circle cx={CX} cy={CY} r={32} fill={QB.green + '15'} stroke={QB.green} strokeWidth="2.5" />
              <text x={CX} y={CY - 2} textAnchor="middle" fill={QB.green} fontSize="14" fontWeight="bold">{'\u2605'}</text>
              <text x={CX} y={CY + 12} textAnchor="middle" fill={QB.green} fontSize="7" fontWeight="600" fontFamily="system-ui">
                {center.name.length > 16 ? center.name.slice(0, 14) + '\u2026' : center.name}
              </text>
            </g>
          );
        })()}

        {/* Entity nodes */}
        {visEnt.map(ent => {
          const ep = pos(ent.id);
          const d = depthMap.get(ent.id) || 1;
          const nodeColor = depthColor(d);
          const sel = selectedId === ent.id;
          const isHovered = hNode === ent.id;
          const isDimmed = (hoverNeighbors && !hoverNeighbors.has(ent.id)) || (scSet && !scSet.has(ent.id));
          const isInChain = scSet && scSet.has(ent.id);
          const r = sel ? 12 : 9;
          const hasNative = nativeOverrideIds.has(ent.id);

          // Volume label — find the highest-volume direct relationship
          const rel = allRelationships.find(rl =>
            (rl.source === ent.id && (rl.target === CENTER_ID || rl.target === hNode)) ||
            (rl.target === ent.id && (rl.source === CENTER_ID || rl.source === hNode))
          );

          return (
            <g key={ent.id}
              onClick={() => pathMode ? onPathSelect(ent.id) : onSelect(ent)}
              onMouseEnter={() => setHNode(ent.id)}
              onMouseLeave={() => setHNode(null)}
              className="cursor-pointer"
              opacity={isDimmed ? 0.1 : 1}
              style={{ transition: 'opacity 0.3s' }}>
              {sel && <circle cx={ep.x} cy={ep.y} r={r + 5} fill="none" stroke={nodeColor} strokeWidth="2" strokeDasharray="4 3" opacity="0.5" />}
              <circle cx={ep.x} cy={ep.y} r={r}
                fill={isInChain ? nodeColor + '35' : nodeColor + '20'}
                stroke={isInChain ? QB.green : nodeColor + (sel ? '' : '80')}
                strokeWidth={isInChain ? 2.5 : sel ? 2 : isHovered ? 1.8 : 1}
                filter={isHovered ? 'url(#shadow)' : undefined} />
              {hasNative && (
                <circle cx={ep.x + r * 0.6} cy={ep.y - r * 0.6} r="3.5" fill={QB.purple} stroke="white" strokeWidth="1" />
              )}
              {/* Label on hover or selected */}
              {(isHovered || sel) && (
                <g>
                  <rect x={ep.x - 55} y={ep.y - r - 24} width="110" height="18" rx="3"
                    fill="white" stroke="#E0E0E0" strokeWidth="0.5" opacity="0.95" />
                  <text x={ep.x} y={ep.y - r - 12} textAnchor="middle" fill={QB.textPrimary} fontSize="9" fontWeight="500" fontFamily="system-ui">
                    {ent.name.length > 22 ? ent.name.slice(0, 20) + '\u2026' : ent.name}
                  </text>
                </g>
              )}
              {/* Depth badge */}
              {d > 1 && !isHovered && !sel && (
                <text x={ep.x} y={ep.y + 3} textAnchor="middle" fill={nodeColor} fontSize="7" fontWeight="600" fontFamily="system-ui">
                  {d}
                </text>
              )}
              {/* Volume label on hover */}
              {isHovered && rel && (
                <text x={ep.x} y={ep.y + r + 12} textAnchor="middle" fill={QB.textMuted} fontSize="8" fontFamily="system-ui">
                  {fmt(rel.volume)}/yr
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Zoom controls */}
      <div className="absolute top-3 right-3 flex flex-col gap-1">
        <button onClick={zoomIn} className="w-8 h-8 flex items-center justify-center rounded bg-white border transition-colors hover:bg-gray-50" style={{ borderColor: QB.cardBorder }} title="Zoom in">
          <ZoomIn size={15} style={{ color: QB.textSecondary }} />
        </button>
        <button onClick={zoomOut} className="w-8 h-8 flex items-center justify-center rounded bg-white border transition-colors hover:bg-gray-50" style={{ borderColor: QB.cardBorder }} title="Zoom out">
          <ZoomOut size={15} style={{ color: QB.textSecondary }} />
        </button>
        <button onClick={zoomReset} className="w-8 h-8 flex items-center justify-center rounded bg-white border transition-colors hover:bg-gray-50" style={{ borderColor: QB.cardBorder }} title="Reset zoom">
          <Maximize2 size={14} style={{ color: QB.textSecondary }} />
        </button>
        <span className="text-center text-[10px] mt-0.5" style={{ color: QB.textMuted }}>{Math.round(zoom * 100)}%</span>
      </div>

      {/* Legend */}
      <div className="graph-legend">
        <span className="flex items-center gap-1">
          <svg width="14" height="14"><circle cx="7" cy="7" r="6" fill={QB.green + '15'} stroke={QB.green} strokeWidth="1.5" /></svg>
          Company
        </span>
        <span className="flex items-center gap-1">
          <svg width="20" height="10"><line x1="0" y1="5" x2="18" y2="5" stroke={VENDOR_COLOR} strokeWidth="2" opacity="0.5" /></svg>
          Vendor
        </span>
        <span className="flex items-center gap-1">
          <svg width="20" height="10"><line x1="0" y1="5" x2="18" y2="5" stroke={CLIENT_COLOR} strokeWidth="2" opacity="0.5" /></svg>
          Client
        </span>
        <span className="flex items-center gap-1">
          <svg width="12" height="12"><circle cx="6" cy="6" r="5" fill={QB.purple + '20'} stroke={QB.purple + '80'} strokeWidth="1" /></svg>
          1-hop
        </span>
        <span className="flex items-center gap-1">
          <svg width="12" height="12"><circle cx="6" cy="6" r="5" fill={QB.orange + '20'} stroke={QB.orange + '80'} strokeWidth="1" /></svg>
          2+ hop
        </span>
        {nativeOverrideIds.size > 0 && (
          <span className="flex items-center gap-1">
            <svg width="12" height="12">
              <circle cx="6" cy="6" r="5" fill="#0284c720" stroke="#0284c780" strokeWidth="1" />
              <circle cx="9" cy="3" r="2.5" fill={QB.purple} stroke="white" strokeWidth="0.5" />
            </svg>
            Override
          </span>
        )}
      </div>
    </div>
  );
}
