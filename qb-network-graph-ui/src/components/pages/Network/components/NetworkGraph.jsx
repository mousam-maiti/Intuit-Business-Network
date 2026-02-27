import { useState, useMemo, useCallback, useRef } from 'react';
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { fmt } from '@/utils/format';
import { config } from '@/config/env';

const CENTER_ID = config.currentEntityId;
const CX = 500, CY = 400;

/**
 * Two-level tree layout:
 *   Center (Company) → Industry group nodes → Entity leaves
 */
function computeTreeLayout(entities, relationships) {
  const positions = new Map();
  const industryNodes = [];   // virtual industry group nodes
  if (!entities.length) return { positions, industryNodes };

  // Separate center from others
  const others = entities.filter(e => e.id !== CENTER_ID);
  positions.set(CENTER_ID, { x: CX, y: CY });

  // Group by industry
  const groups = {};
  others.forEach(e => {
    const key = e.industry || '_none';
    if (!groups[key]) groups[key] = [];
    groups[key].push(e);
  });

  const groupKeys = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);
  const groupCount = groupKeys.length;

  // Industry nodes sit on a ring around center
  const industryR = 220;
  // Entity leaves fan out behind their industry node
  const leafBaseR = 120;
  const leafMaxR = 200;

  groupKeys.forEach((key, gi) => {
    const angle = (2 * Math.PI * gi) / groupCount - Math.PI / 2;
    const ind = getIndustry(key === '_none' ? null : key);
    const group = groups[key];

    // Industry node position
    const ix = CX + industryR * Math.cos(angle);
    const iy = CY + industryR * Math.sin(angle);
    const industryId = `__ind_${key}`;

    positions.set(industryId, { x: ix, y: iy });
    industryNodes.push({
      id: industryId,
      label: ind.label,
      color: ind.color,
      count: group.length,
      naics: key,
    });

    // Fan entities outward from the industry node
    // Spread angle proportional to group size, but capped
    const fanAngle = Math.min(Math.PI * 0.6, 0.15 + group.length * 0.08);

    // Sort by volume desc — higher volume closer
    group.sort((a, b) => (b.volume || 0) - (a.volume || 0));

    group.forEach((e, i) => {
      const frac = group.length > 1 ? i / (group.length - 1) : 0.5;
      const r = leafBaseR + (leafMaxR - leafBaseR) * frac;
      const leafAngle = group.length > 1
        ? angle + fanAngle * (i / (group.length - 1) - 0.5)
        : angle;
      positions.set(e.id, {
        x: ix + r * Math.cos(leafAngle),
        y: iy + r * Math.sin(leafAngle),
      });
    });
  });

  return { positions, industryNodes };
}

export function NetworkGraph({ selectedId, onSelect, depth, pathNodes, pathMode, onPathSelect, edgeFilter, showDormant, nativeOverrides = {}, nativeMerges = [], allEntities = [], allRelationships = [] }) {
  const [hNode, setHNode] = useState(null);
  const [hIndustry, setHIndustry] = useState(null);
  const [zoom, setZoom] = useState(1);
  const svgRef = useRef(null);

  const zoomIn = useCallback(() => setZoom(z => Math.min(z * 1.25, 4)), []);
  const zoomOut = useCallback(() => setZoom(z => Math.max(z / 1.25, 0.25)), []);
  const zoomReset = useCallback(() => setZoom(1), []);

  const handleWheel = useCallback((e) => {
    e.preventDefault();
    setZoom(z => {
      const factor = e.deltaY < 0 ? 1.08 : 1 / 1.08;
      return Math.min(Math.max(z * factor, 0.25), 4);
    });
  }, []);

  // Compute tree layout
  const { positions, industryNodes } = useMemo(
    () => computeTreeLayout(allEntities, allRelationships),
    [allEntities, allRelationships]
  );

  // Map entity id → industry group id
  const entityToIndustry = useMemo(() => {
    const map = {};
    allEntities.forEach(e => {
      if (e.id === CENTER_ID) return;
      map[e.id] = `__ind_${e.industry || '_none'}`;
    });
    return map;
  }, [allEntities]);

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

  // Filter industry nodes to only those with visible entities, with updated counts
  const visIndustryNodes = useMemo(() => {
    if (edgeFilter === 'all') return industryNodes;
    const countByInd = {};
    visEnt.forEach(e => {
      const indId = `__ind_${e.industry || '_none'}`;
      countByInd[indId] = (countByInd[indId] || 0) + 1;
    });
    return industryNodes
      .filter(n => countByInd[n.id])
      .map(n => ({ ...n, count: countByInd[n.id] }));
  }, [industryNodes, visEnt, edgeFilter]);

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

  // Highlighted industry (when hovering an industry node)
  const highlightedEntities = useMemo(() => {
    if (!hIndustry) return null;
    const set = new Set();
    allEntities.forEach(e => {
      if (entityToIndustry[e.id] === hIndustry) set.add(e.id);
    });
    return set;
  }, [hIndustry, allEntities, entityToIndustry]);

  return (
    <div className="graph-container">
      <svg ref={svgRef} onWheel={handleWheel}
        viewBox={`${vb.x + vb.w * (1 - 1 / zoom) / 2} ${vb.y + vb.h * (1 - 1 / zoom) / 2} ${vb.w / zoom} ${vb.h / zoom}`}
        className="w-full h-full" style={{ background: '#FAFBFC' }}>
        <defs>
          <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="1" stdDeviation="2" floodOpacity="0.1" />
          </filter>
        </defs>

        {/* Level 1 edges: Center → Industry nodes */}
        {visIndustryNodes.map(ind => {
          const ip = pos(ind.id);
          const dx = ip.x - CX, dy = ip.y - CY;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const ux = dx / dist, uy = dy / dist;
          return (
            <line key={`c-${ind.id}`}
              x1={CX + ux * 30} y1={CY + uy * 30}
              x2={ip.x - ux * 24} y2={ip.y - uy * 24}
              stroke={ind.color} strokeWidth={2 + ind.count * 0.3}
              strokeOpacity={hIndustry && hIndustry !== ind.id ? 0.08 : 0.3}
              className="transition-all duration-300"
            />
          );
        })}

        {/* Level 2 edges: Industry → Entity leaves */}
        {visEnt.map(ent => {
          const indId = entityToIndustry[ent.id];
          const ind = industryNodes.find(n => n.id === indId);
          if (!ind) return null;
          const ip = pos(indId);
          const ep = pos(ent.id);
          const dx = ep.x - ip.x, dy = ep.y - ip.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const ux = dx / dist, uy = dy / dist;

          // Find the actual relationship for this entity to get volume
          const rel = allRelationships.find(r =>
            (r.source === CENTER_ID && r.target === ent.id) ||
            (r.target === CENTER_ID && r.source === ent.id)
          );
          const w = rel ? Math.max(1, (rel.volume / mx) * 4) : 1;
          const isHovered = hNode === ent.id;
          const isDimmed = (hIndustry && indId !== hIndustry) || (hNode && hNode !== ent.id && entityToIndustry[hNode] !== indId);

          return (
            <line key={`l-${ent.id}`}
              x1={ip.x + ux * 22} y1={ip.y + uy * 22}
              x2={ep.x - ux * 12} y2={ep.y - uy * 12}
              stroke={ind.color}
              strokeWidth={isHovered ? w + 1.5 : w}
              strokeOpacity={isDimmed ? 0.06 : isHovered ? 0.7 : 0.2}
              className="transition-all duration-300"
            />
          );
        })}

        {/* Industry group nodes */}
        {visIndustryNodes.map(ind => {
          const ip = pos(ind.id);
          const r = 18 + Math.min(ind.count, 10) * 1.5;
          const isHovered = hIndustry === ind.id;

          return (
            <g key={ind.id}
              onMouseEnter={() => setHIndustry(ind.id)}
              onMouseLeave={() => setHIndustry(null)}
              className="cursor-pointer"
              opacity={hIndustry && hIndustry !== ind.id ? 0.2 : 1}
              style={{ transition: 'opacity 0.3s' }}>
              {isHovered && <circle cx={ip.x} cy={ip.y} r={r + 4} fill="none" stroke={ind.color} strokeWidth="2" strokeDasharray="4 3" opacity="0.4" />}
              <circle cx={ip.x} cy={ip.y} r={r}
                fill={ind.color + '20'} stroke={ind.color} strokeWidth={isHovered ? 2 : 1.2}
                filter={isHovered ? 'url(#shadow)' : undefined} />
              <text x={ip.x} y={ip.y - 1} textAnchor="middle" fill={ind.color} fontSize="10" fontWeight="600" fontFamily="system-ui">
                {ind.count}
              </text>
              <text x={ip.x} y={ip.y + 9} textAnchor="middle" fill={ind.color} fontSize="7" fontFamily="system-ui" opacity="0.8">
                entities
              </text>
              {/* Label below */}
              <text x={ip.x} y={ip.y + r + 14} textAnchor="middle" fill={QB.textPrimary} fontSize="9" fontWeight="500" fontFamily="system-ui">
                {ind.label.length > 18 ? ind.label.slice(0, 16) + '\u2026' : ind.label}
              </text>
            </g>
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

        {/* Entity leaf nodes */}
        {visEnt.map(ent => {
          const ep = pos(ent.id);
          const ind = getIndustry(ent.industry);
          const sel = selectedId === ent.id;
          const indId = entityToIndustry[ent.id];
          const isHovered = hNode === ent.id;
          const isDimmed = (hIndustry && indId !== hIndustry) || (hNode && hNode !== ent.id && entityToIndustry[hNode] !== indId);
          const r = sel ? 12 : 9;
          const hasNative = nativeOverrideIds.has(ent.id);

          const rel = allRelationships.find(rl =>
            (rl.source === CENTER_ID && rl.target === ent.id) ||
            (rl.target === CENTER_ID && rl.source === ent.id)
          );

          return (
            <g key={ent.id}
              onClick={() => pathMode ? onPathSelect(ent.id) : onSelect(ent)}
              onMouseEnter={() => setHNode(ent.id)}
              onMouseLeave={() => setHNode(null)}
              className="cursor-pointer"
              opacity={isDimmed ? 0.1 : 1}
              style={{ transition: 'opacity 0.3s' }}>
              {sel && <circle cx={ep.x} cy={ep.y} r={r + 5} fill="none" stroke={ind.color} strokeWidth="2" strokeDasharray="4 3" opacity="0.5" />}
              <circle cx={ep.x} cy={ep.y} r={r}
                fill={ind.color + '20'} stroke={ind.color + (sel ? '' : '80')}
                strokeWidth={sel ? 2 : isHovered ? 1.8 : 1}
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
          <svg width="14" height="14"><circle cx="7" cy="7" r="5" fill={QB.purple + '20'} stroke={QB.purple} strokeWidth="1.2" /><text x="7" y="10" textAnchor="middle" fill={QB.purple} fontSize="7" fontWeight="600">3</text></svg>
          Industry
        </span>
        <span className="flex items-center gap-1">
          <svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="#0284c720" stroke="#0284c780" strokeWidth="1" /></svg>
          Entity
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
