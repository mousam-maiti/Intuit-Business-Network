import { useState, useMemo, useRef, useEffect } from 'react';
import { Search, Building2, ChevronRight, SortAsc, X } from 'lucide-react';
import { QB } from '@/constants/colors';
import { INDUSTRIES, getIndustry } from '@/constants/industries';
import { fmt } from '@/utils/format';
import { getRelType } from '@/utils/graph';
import { getNativeOverrides, saveNativeOverride } from '@/api/native';
import { Widget, RelTypeBadge, EntityDetailPanel } from '@/components/shared';

export default function SearchPage({ onNavigate, networkEntities = [], networkRelationships = [] }) {
  const [q, setQ] = useState('');
  const [indFilter, setIndFilter] = useState(null);
  const [typeFilter, setTypeFilter] = useState('all');
  const [sortBy, setSortBy] = useState('relevance');
  const [showTypeahead, setShowTypeahead] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState(null);
  const inputRef = useRef(null);

  const [nativeOverrides, setNativeOverrides] = useState({});
  useEffect(() => {
    getNativeOverrides().then(r => setNativeOverrides(r.data));
  }, []);

  const handleSaveNative = async (entityId, overrides) => {
    if (overrides) {
      await saveNativeOverride(entityId, overrides);
      setNativeOverrides((prev) => ({ ...prev, [entityId]: overrides }));
    } else {
      setNativeOverrides((prev) => { const next = { ...prev }; delete next[entityId]; return next; });
    }
  };

  const typeaheadResults = useMemo(() => {
    if (q.length < 2) return [];
    const lower = q.toLowerCase();
    return networkEntities.filter((e) =>
      e.name.toLowerCase().includes(lower) ||
      (e.variants || []).some((v) => v.toLowerCase().includes(lower)) ||
      getIndustry(e.industry).label.toLowerCase().includes(lower)
    ).slice(0, 5);
  }, [q, networkEntities]);

  const selectedEntityId = networkEntities.length > 0 ? networkEntities[0]?.id : null;

  const filtered = useMemo(() => {
    let list = networkEntities.filter((e) => {
      const mq = !q || e.name.toLowerCase().includes(q.toLowerCase()) || getIndustry(e.industry).label.toLowerCase().includes(q.toLowerCase());
      const mi = !indFilter || e.industry === indFilter;
      if (typeFilter !== 'all' && selectedEntityId) {
        const hasType = networkRelationships.some((r) => {
          if (typeFilter === 'vendor') return r.source === selectedEntityId && r.target === e.id;
          return r.target === selectedEntityId && r.source === e.id;
        });
        if (!hasType) return false;
      }
      return mq && mi;
    });
    if (sortBy === 'volume') list = [...list].sort((a, b) => b.volume - a.volume);
    if (sortBy === 'connections') list = [...list].sort((a, b) => (b.vendors + b.clients) - (a.vendors + a.clients));
    if (sortBy === 'confidence') list = [...list].sort((a, b) => b.confidence - a.confidence);
    return list;
  }, [q, indFilter, typeFilter, sortBy, networkEntities, networkRelationships, selectedEntityId]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4">
        <h1 className="text-xl font-normal mb-3" style={{ color: QB.textPrimary }}>Search network</h1>
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: QB.textMuted }} />
          <input ref={inputRef} type="text" value={q}
            onChange={(e) => { setQ(e.target.value); setShowTypeahead(true); }}
            onFocus={() => setShowTypeahead(true)}
            onBlur={() => setTimeout(() => setShowTypeahead(false), 200)}
            placeholder="Search businesses, industries, commodities..."
            className="w-full pl-10 pr-4 py-2.5 rounded border text-sm focus:outline-none focus:ring-2" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
          {showTypeahead && typeaheadResults.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white border rounded shadow-lg z-30 overflow-hidden" style={{ borderColor: QB.cardBorder }}>
              <div className="px-3 py-1.5 text-[10px] font-semibold tracking-wider" style={{ backgroundColor: '#F9FAFB', color: QB.textMuted, letterSpacing: '0.08em' }}>SUGGESTIONS &middot; &lt;30ms typeahead</div>
              {typeaheadResults.map((ent) => {
                const ind = getIndustry(ent.industry);
                const dr = selectedEntityId ? networkRelationships.find((r) => (r.source === selectedEntityId && r.target === ent.id) || (r.target === selectedEntityId && r.source === ent.id)) : null;
                return (
                  <div key={ent.id} onMouseDown={() => { setQ(ent.name); setShowTypeahead(false); setSelectedEntity(ent); }}
                    className="flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-gray-50 border-b" style={{ borderColor: '#F0F0F0' }}>
                    <div className="w-7 h-7 rounded flex items-center justify-center" style={{ backgroundColor: ind.color + '12' }}><Building2 size={12} style={{ color: ind.color }} /></div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate" style={{ color: QB.textPrimary }}>{ent.name}</div>
                      <div className="text-[10px]" style={{ color: QB.textMuted }}>{ind.label} &middot; {ent.city}, {ent.state}</div>
                    </div>
                    {dr && <RelTypeBadge type={getRelType(dr, selectedEntityId)} />}
                    <ChevronRight size={12} style={{ color: QB.textMuted }} />
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
      <div className="flex-1 flex min-h-0 px-6 pb-4 gap-4">
        <div className="w-48 space-y-3 shrink-0">
          <Widget title="RELATIONSHIP">
            <div className="space-y-0.5">
              {[{ k: 'all', l: 'All types' }, { k: 'vendor', l: 'My vendors' }, { k: 'client', l: 'My clients' }].map((f) => (
                <button key={f.k} onClick={() => setTypeFilter(f.k)}
                  className="w-full flex items-center gap-2 text-xs px-2 py-1.5 rounded transition-colors text-left"
                  style={{ backgroundColor: typeFilter === f.k ? QB.purpleLight : 'transparent', color: typeFilter === f.k ? QB.purpleDark : QB.textSecondary }}>
                  {f.k === 'vendor' && <span style={{ color: QB.purple }}>{'\u2190'}</span>}
                  {f.k === 'client' && <span style={{ color: QB.green }}>{'\u2192'}</span>}
                  {f.l}
                </button>
              ))}
            </div>
          </Widget>
          <Widget title="INDUSTRY">
            <div className="space-y-0.5">
              {Object.entries(INDUSTRIES).slice(0, 6).map(([code, ind]) => {
                const cnt = networkEntities.filter((e) => e.industry === code).length;
                if (!cnt) return null;
                return (
                  <button key={code} onClick={() => setIndFilter(indFilter === code ? null : code)}
                    className="w-full flex items-center gap-2 text-xs px-2 py-1.5 rounded transition-colors text-left"
                    style={{ backgroundColor: indFilter === code ? QB.greenLight : 'transparent', color: indFilter === code ? QB.greenDark : QB.textSecondary }}>
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: ind.color }} />
                    <span className="flex-1 truncate">{ind.label}</span>
                    <span style={{ color: QB.textMuted }}>{cnt}</span>
                  </button>
                );
              })}
            </div>
          </Widget>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs" style={{ color: QB.textMuted }}>Showing {filtered.length} results{q ? ' for "' + q + '"' : ''}</p>
            <div className="flex items-center gap-1 text-xs">
              <SortAsc size={12} style={{ color: QB.textMuted }} />
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="text-xs bg-transparent border-none focus:outline-none cursor-pointer" style={{ color: QB.textSecondary }}>
                <option value="relevance">Relevance</option><option value="volume">Volume</option><option value="connections">Connections</option><option value="confidence">Confidence</option>
              </select>
            </div>
          </div>
          {filtered.map((ent) => {
            const ind = getIndustry(ent.industry);
            const dr = selectedEntityId ? networkRelationships.find((r) => (r.source === selectedEntityId && r.target === ent.id) || (r.target === selectedEntityId && r.source === ent.id)) : null;
            return (
              <div key={ent.id} onClick={() => setSelectedEntity(ent)}
                className="p-4 bg-white border rounded-sm cursor-pointer transition-all hover:shadow-sm group"
                style={{ borderColor: selectedEntity?.id === ent.id ? QB.green + '60' : QB.cardBorder, backgroundColor: selectedEntity?.id === ent.id ? '#F9FAFB' : undefined }}>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded flex items-center justify-center" style={{ backgroundColor: ind.color + '12' }}><Building2 size={14} style={{ color: ind.color }} /></div>
                    <div>
                      <div className="text-sm font-medium group-hover:underline" style={{ color: QB.link }}>{ent.name}</div>
                      <div className="text-[11px]" style={{ color: QB.textMuted }}>{ind.label} &middot; {ent.city}, {ent.state} &middot; {ent.vendors + ent.clients} connections</div>
                    </div>
                  </div>
                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded" style={{ backgroundColor: ent.confidence >= 0.9 ? QB.greenLight : QB.orangeLight, color: ent.confidence >= 0.9 ? QB.greenDark : QB.orange }}>{Math.round(ent.confidence * 100)}%</span>
                </div>
                {dr && (
                  <div className="text-[11px] mt-2 flex items-center gap-2">
                    <RelTypeBadge type={getRelType(dr, selectedEntityId)} />
                    <span style={{ color: QB.textMuted }}>{fmt(dr.volume)}/yr &middot; {dr.count} transactions</span>
                    {dr.status === 'dormant' && <span className="text-[9px] px-1 rounded" style={{ backgroundColor: '#F0F0F0', color: QB.dormant }}>dormant</span>}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Entity detail panel */}
        {selectedEntity && (
          <div className="w-80 flex flex-col gap-3 overflow-y-auto shrink-0">
            <div className="flex items-center justify-end">
              <button onClick={() => setSelectedEntity(null)} className="p-1 rounded hover:bg-gray-100">
                <X size={14} style={{ color: QB.textMuted }} />
              </button>
            </div>
            <EntityDetailPanel
              globalEntity={selectedEntity}
              nativeOverride={nativeOverrides[selectedEntity.id] || null}
              onSaveNative={handleSaveNative}
              onOpenAI={() => onNavigate('assist', selectedEntity)}
              onShowOnNetwork={() => onNavigate('network', selectedEntity)}
              onMerge={() => {}}
              onSelectEntity={setSelectedEntity}
              vendorRels={networkRelationships.filter((r) => r.source === selectedEntity.id).sort((a, b) => b.volume - a.volume)}
              clientRels={networkRelationships.filter((r) => r.target === selectedEntity.id).sort((a, b) => b.volume - a.volume)}
              allEntities={networkEntities}
            />
          </div>
        )}
      </div>
    </div>
  );
}
