import { useState, useCallback } from 'react';
import { Eye, EyeOff, X, Navigation, Sparkles, Building2 } from 'lucide-react';
import { BarChart, Bar, XAxis, ResponsiveContainer, Cell } from 'recharts';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { fmt } from '@/utils/format';
import { findPath } from '@/utils/graph';
import { ENTITIES, RELATIONSHIPS, MONTHLY_VOLUME } from '@/api/mock/data';
import { Widget } from '@/components/shared';
import { NetworkGraph } from './components/NetworkGraph';

export default function NetworkPage({ selectedEntity, onSelect, onOpenAI, privacy }) {
  const [depth, setDepth] = useState(2);
  const [edgeFilter, setEdgeFilter] = useState('all');
  const [showDormant, setShowDormant] = useState(true);
  const [pathMode, setPathMode] = useState(false);
  const [pathStart, setPathStart] = useState(null);
  const [pathEnd, setPathEnd] = useState(null);
  const [pathResult, setPathResult] = useState(null);
  const [showProfile, setShowProfile] = useState(false);

  const handlePathSelect = useCallback((id) => {
    if (!pathStart) {
      setPathStart(id); setPathEnd(null); setPathResult(null);
    } else if (id !== pathStart) {
      setPathEnd(id);
      setPathResult(findPath(RELATIONSHIPS, pathStart, id));
    }
  }, [pathStart]);

  const clearPath = () => { setPathMode(false); setPathStart(null); setPathEnd(null); setPathResult(null); };

  const rels = selectedEntity ? RELATIONSHIPS.filter((r) => r.source === selectedEntity.id || r.target === selectedEntity.id).sort((a, b) => b.volume - a.volume) : [];
  const vendorRels = rels.filter((r) => r.source === selectedEntity?.id);
  const clientRels = rels.filter((r) => r.target === selectedEntity?.id);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-6 py-3">
        <h1 className="text-xl font-normal" style={{ color: QB.textPrimary }}>Business network</h1>
        <div className="flex items-center gap-3 text-xs">
          <div className="flex border rounded" style={{ borderColor: QB.cardBorder }}>
            {[{ k: 'all', l: 'All' }, { k: 'vendor', l: 'Vendors' }, { k: 'client', l: 'Clients' }].map((f) => (
              <button key={f.k} onClick={() => setEdgeFilter(f.k)} className="px-2.5 py-1.5 text-xs transition-colors"
                style={{ backgroundColor: edgeFilter === f.k ? QB.purple : 'white', color: edgeFilter === f.k ? 'white' : QB.textSecondary, borderRight: f.k !== 'client' ? '1px solid ' + QB.cardBorder : 'none' }}>
                {f.l}
              </button>
            ))}
          </div>
          <button onClick={() => setShowDormant(!showDormant)} className="flex items-center gap-1 px-2 py-1.5 rounded border transition-colors"
            style={{ borderColor: QB.cardBorder, backgroundColor: showDormant ? 'white' : '#F4F5F7', color: showDormant ? QB.textSecondary : QB.textMuted }}>
            {showDormant ? <Eye size={12} /> : <EyeOff size={12} />} Dormant
          </button>
          <button onClick={() => pathMode ? clearPath() : setPathMode(true)}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded transition-colors"
            style={{ backgroundColor: pathMode ? QB.orange + '15' : 'white', color: pathMode ? QB.orange : QB.textSecondary, border: '1px solid ' + (pathMode ? QB.orange + '50' : QB.cardBorder) }}>
            <Navigation size={12} /> {pathMode ? 'Exit path mode' : 'Find path'}
          </button>
          <span className="text-[1px]" style={{ color: QB.cardBorder }}>|</span>
          <span style={{ color: QB.textMuted }}>Depth:</span>
          <div className="flex border rounded" style={{ borderColor: QB.cardBorder }}>
            {[{ d: 1, c: QB.purple }, { d: 2, c: QB.orange }, { d: 3, c: QB.link }].map(({ d, c }) => (
              <button key={d} onClick={() => setDepth(d)} className="px-3 py-1.5 text-xs transition-colors"
                style={{ backgroundColor: depth === d ? c : 'white', color: depth === d ? 'white' : QB.textSecondary, borderRight: d < 3 ? '1px solid ' + QB.cardBorder : 'none' }}>
                {d}-hop
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Path mode banner */}
      {pathMode && (
        <div className="mx-6 mb-2 flex items-center gap-3 px-4 py-2 rounded text-xs" style={{ backgroundColor: QB.orange + '10', border: '1px solid ' + QB.orange + '30', color: QB.orange }}>
          <Navigation size={13} />
          <span className="flex-1">
            {!pathStart ? 'Click a starting entity on the graph' :
              !pathEnd ? (<>Start: <strong>{ENTITIES.find((e) => e.id === pathStart)?.name}</strong> &mdash; Now click the destination</>) :
                pathResult ? (<>Path: {pathResult.map((id, i) => (<span key={id}>{i > 0 && ' \u2192 '}<strong>{ENTITIES.find((e) => e.id === id)?.name}</strong></span>))} <span style={{ color: QB.textMuted }}>&middot; {pathResult.length - 1} hop{pathResult.length > 2 ? 's' : ''} &middot; BFS &lt;30ms</span></>) :
                  <span style={{ color: QB.red }}>No path found between these entities</span>}
          </span>
          {pathResult && <button onClick={() => { setPathStart(null); setPathEnd(null); setPathResult(null); }} className="text-[10px] px-2 py-1 rounded" style={{ backgroundColor: QB.orange + '20' }}>Reset</button>}
          <button onClick={clearPath} className="p-0.5"><X size={13} /></button>
        </div>
      )}

      {/* Graph + sidebar */}
      <div className="flex-1 flex min-h-0 px-6 pb-4 gap-4">
        <div className="flex-1">
          <NetworkGraph selectedId={selectedEntity?.id} onSelect={onSelect} depth={depth}
            pathNodes={pathResult} pathMode={pathMode} onPathSelect={handlePathSelect}
            edgeFilter={edgeFilter} showDormant={showDormant} privacy={privacy} />
        </div>

        {selectedEntity && (
          <div className="w-80 flex flex-col gap-3 overflow-y-auto">
            {/* Entity details */}
            <Widget title="SELECTED ENTITY" action={
              <button onClick={() => setShowProfile(!showProfile)} className="text-[10px]" style={{ color: QB.link }}>
                {showProfile ? 'Less' : 'Full profile'} {showProfile ? '\u25B4' : '\u25BE'}
              </button>
            }>
              <div className="flex items-center gap-3 mb-3">
                <div className="w-9 h-9 rounded flex items-center justify-center" style={{ backgroundColor: getIndustry(selectedEntity.industry).color + '15' }}>
                  <Building2 size={16} style={{ color: getIndustry(selectedEntity.industry).color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate" style={{ color: QB.textPrimary }}>{selectedEntity.name}</div>
                  <div className="text-[11px]" style={{ color: QB.textMuted }}>{getIndustry(selectedEntity.industry).label} &middot; {selectedEntity.city}, {selectedEntity.state}</div>
                </div>
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0"
                  style={{ backgroundColor: selectedEntity.confidence >= 0.9 ? QB.greenLight : QB.orangeLight, color: selectedEntity.confidence >= 0.9 ? QB.greenDark : QB.orange }}>
                  {Math.round(selectedEntity.confidence * 100)}%
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 mb-3">
                {[{ l: 'Vendors', v: selectedEntity.vendors, c: QB.purple }, { l: 'Clients', v: selectedEntity.clients, c: QB.green }, { l: 'Volume', v: fmt(selectedEntity.volume), c: QB.link }].map((s, i) => (
                  <div key={i} className="text-center py-2 rounded" style={{ backgroundColor: '#F4F5F7' }}>
                    <div className="text-sm font-semibold" style={{ color: s.c }}>{s.v}</div>
                    <div className="text-[10px]" style={{ color: QB.textMuted }}>{s.l}</div>
                  </div>
                ))}
              </div>
              {showProfile && (
                <div className="space-y-2.5 pt-2 border-t" style={{ borderColor: QB.cardBorder }}>
                  <div className="text-[10px] font-semibold tracking-wider" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>ENTITY PERSONA</div>
                  {[
                    { l: 'Legal structure', v: selectedEntity.legalStructure },
                    { l: 'NAICS code', v: selectedEntity.naics + ' \u2014 ' + getIndustry(selectedEntity.industry).label },
                    { l: 'Service area', v: selectedEntity.serviceArea },
                    { l: 'Name variants', v: selectedEntity.variants.map((v) => '"' + v + '"').join(', ') },
                  ].map((row, i) => (
                    <div key={i} className="text-xs">
                      <span style={{ color: QB.textMuted }}>{row.l}: </span>
                      <span style={{ color: QB.textPrimary }}>{row.v}</span>
                    </div>
                  ))}
                  <div className="text-xs">
                    <span style={{ color: QB.textMuted }}>Commodities: </span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {selectedEntity.commodities.map((c, i) => (
                        <span key={i} className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: '#F0F1F3', color: QB.textSecondary }}>{c}</span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
              <button onClick={() => onOpenAI?.(selectedEntity)} className="w-full text-xs py-2 rounded flex items-center justify-center gap-1.5 mt-3" style={{ backgroundColor: QB.greenLight, color: QB.greenDark }}>
                <Sparkles size={11} /> Ask Intuit Assist
              </button>
            </Widget>

            <Widget title="TRANSACTION VOLUME">
              <div className="h-20">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={MONTHLY_VOLUME}>
                    <XAxis dataKey="month" tick={{ fontSize: 9, fill: QB.textMuted }} axisLine={false} tickLine={false} />
                    <Bar dataKey="vol" radius={[2, 2, 0, 0]}>
                      {MONTHLY_VOLUME.map((_, i) => <Cell key={i} fill={i % 2 === 0 ? QB.green : QB.purple} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Widget>

            <Widget title={'VENDORS (' + vendorRels.length + ')'}>
              <div className="space-y-1.5">
                {vendorRels.slice(0, 4).map((rel, i) => {
                  const o = ENTITIES.find((e) => e.id === rel.target);
                  return (
                    <div key={i} className="flex items-center gap-2 text-xs py-1.5 border-b cursor-pointer hover:bg-gray-50 -mx-1 px-1 rounded" style={{ borderColor: '#F0F0F0' }} onClick={() => o && onSelect(o)}>
                      <span className="text-[10px] px-1 py-0.5 rounded font-medium" style={{ backgroundColor: QB.purpleLight, color: QB.purpleDark }}>{'\u2190'} V</span>
                      <span className="flex-1 truncate" style={{ color: QB.textPrimary }}>{o?.name}</span>
                      {rel.status === 'dormant' && <span className="text-[9px] px-1 rounded" style={{ backgroundColor: '#F0F0F0', color: QB.dormant }}>dormant</span>}
                      <span style={{ color: QB.textMuted }}>{fmt(rel.volume)}</span>
                    </div>
                  );
                })}
              </div>
            </Widget>

            <Widget title={'CLIENTS (' + clientRels.length + ')'}>
              <div className="space-y-1.5">
                {clientRels.slice(0, 4).map((rel, i) => {
                  const o = ENTITIES.find((e) => e.id === rel.source);
                  return (
                    <div key={i} className="flex items-center gap-2 text-xs py-1.5 border-b cursor-pointer hover:bg-gray-50 -mx-1 px-1 rounded" style={{ borderColor: '#F0F0F0' }} onClick={() => o && onSelect(o)}>
                      <span className="text-[10px] px-1 py-0.5 rounded font-medium" style={{ backgroundColor: QB.greenLight, color: QB.greenDark }}>{'\u2192'} C</span>
                      <span className="flex-1 truncate" style={{ color: QB.textPrimary }}>{o?.name}</span>
                      {rel.status === 'dormant' && <span className="text-[9px] px-1 rounded" style={{ backgroundColor: '#F0F0F0', color: QB.dormant }}>dormant</span>}
                      <span style={{ color: QB.textMuted }}>{fmt(rel.volume)}</span>
                    </div>
                  );
                })}
              </div>
            </Widget>
          </div>
        )}
      </div>
    </div>
  );
}
