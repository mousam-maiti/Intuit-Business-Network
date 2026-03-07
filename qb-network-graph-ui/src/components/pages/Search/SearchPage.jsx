import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Search, Building2, ChevronRight, SortAsc, X, Loader2 } from 'lucide-react';
import { QB } from '@/constants/colors';
import { INDUSTRIES, getIndustry } from '@/constants/industries';
import { fmt } from '@/utils/format';
import { getRelType } from '@/utils/graph';
import { config } from '@/config/env';
import { searchEntities } from '@/api/search';
import { addConnection, addExistingConnection, removeConnection } from '@/api/connections';
import { getNativeOverrides, saveNativeOverride, createNativeMerge, undoNativeMerge } from '@/api/native';
import { Widget, RelTypeBadge, EntityDetailPanel, MergeFlowModal } from '@/components/shared';

function AddConnectionModal({ entity, onConfirm, onClose }) {
  const [connType, setConnType] = useState(null);
  const [adding, setAdding] = useState(false);

  const handleAdd = async () => {
    setAdding(true);
    try {
      await onConfirm(entity, connType);
      onClose();
    } catch (err) {
      console.error('Failed to add connection:', err);
      setAdding(false);
    }
  };

  const ind = getIndustry(entity.industry);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-96 p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: QB.textPrimary }}>Add to your network</h3>
        <div className="flex items-center gap-3 mb-4 p-3 rounded" style={{ backgroundColor: '#F9FAFB' }}>
          <div className="w-8 h-8 rounded flex items-center justify-center" style={{ backgroundColor: ind.color + '12' }}>
            <Building2 size={14} style={{ color: ind.color }} />
          </div>
          <div>
            <div className="text-sm font-medium" style={{ color: QB.textPrimary }}>{entity.name}</div>
            <div className="text-[11px]" style={{ color: QB.textMuted }}>{ind.label} &middot; {entity.city}, {entity.state}</div>
          </div>
        </div>
        <p className="text-xs mb-3" style={{ color: QB.textSecondary }}>Add as:</p>
        <div className="flex gap-2 mb-4">
          <button onClick={() => setConnType('vendor')}
            className="flex-1 py-2.5 rounded border text-xs font-medium transition-colors"
            style={{
              borderColor: connType === 'vendor' ? QB.purple : QB.cardBorder,
              backgroundColor: connType === 'vendor' ? QB.purpleLight : 'white',
              color: connType === 'vendor' ? QB.purpleDark : QB.textSecondary,
            }}>
            {'\u2190'} Vendor
          </button>
          <button onClick={() => setConnType('client')}
            className="flex-1 py-2.5 rounded border text-xs font-medium transition-colors"
            style={{
              borderColor: connType === 'client' ? QB.green : QB.cardBorder,
              backgroundColor: connType === 'client' ? QB.greenLight : 'white',
              color: connType === 'client' ? QB.greenDark : QB.textSecondary,
            }}>
            Client {'\u2192'}
          </button>
        </div>
        <p className="text-[10px] mb-4" style={{ color: QB.textMuted }}>
          This will add {entity.name} and all their connections to your network.
        </p>
        <div className="flex gap-2">
          <button onClick={onClose}
            className="flex-1 text-xs py-2 rounded border transition-colors hover:bg-gray-50"
            style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
            Cancel
          </button>
          <button onClick={handleAdd} disabled={!connType || adding}
            className="flex-1 text-xs py-2 rounded text-white transition-colors disabled:opacity-50"
            style={{ backgroundColor: QB.green }}>
            {adding ? 'Adding...' : 'Add to network'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function SearchPage({ onNavigate, networkRelationships = [], refreshNetwork }) {
  const [q, setQ] = useState('');
  const [indFilter, setIndFilter] = useState(null);
  const [networkFilter, setNetworkFilter] = useState('all');
  const [sortBy, setSortBy] = useState('relevance');
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [cached, setCached] = useState(false);
  const [addTarget, setAddTarget] = useState(null);
  const inputRef = useRef(null);
  const debounceRef = useRef(null);

  const [nativeOverrides, setNativeOverrides] = useState({});
  const [mergeSource, setMergeSource] = useState(null);

  useEffect(() => {
    getNativeOverrides().then(r => setNativeOverrides(r.data));
  }, []);

  const selectedEntityId = config.currentEntityId;

  // Set of entity IDs in the user's extended network (all hops)
  const networkEntityIds = useMemo(() => {
    const ids = new Set();
    ids.add(selectedEntityId);
    networkRelationships.forEach((r) => {
      ids.add(r.source);
      ids.add(r.target);
    });
    return ids;
  }, [networkRelationships, selectedEntityId]);

  // Debounced search
  const doSearch = useCallback(async (query, industry, sort) => {
    try {
      setLoading(true);
      const res = await searchEntities(query, {
        industry: industry || undefined,
        sortBy: sort !== 'relevance' ? sort : undefined,
        limit: 100,
      });
      setResults(res.data || []);
      setCached(res.cached || false);
      setSearched(true);
    } catch (err) {
      console.error('Search failed:', err);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q && !indFilter) {
      setResults([]);
      setSearched(false);
      return;
    }
    debounceRef.current = setTimeout(() => {
      doSearch(q, indFilter, sortBy);
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [q, indFilter, sortBy, doSearch]);

  const handleAddConnection = async (entity, connType) => {
    if (entity.id?.startsWith('G-')) {
      // Entity already exists as a golden record — add directly + pull neighbors
      await addExistingConnection(entity.id, connType);
    } else {
      // New entity — go through entity resolution pipeline
      await addConnection({
        connType,
        entity,
        name: entity.name,
        ein: entity.ein?.replace(/-/g, ''),
        contactName: entity.contactName,
        email: entity.email,
        phone: entity.phone,
        category: entity.industry,
        commodity: entity.commodities?.join('; '),
        city: entity.city,
        state: entity.state,
        zip: entity.zip,
      });
    }
    // Refresh network so the badge updates immediately
    if (refreshNetwork) await refreshNetwork();
  };

  const [removing, setRemoving] = useState(null);

  const handleRemoveConnection = async (e, entity) => {
    if (e) e.stopPropagation();
    setRemoving(entity.id);
    try {
      await removeConnection(entity.id);
      if (refreshNetwork) await refreshNetwork();
    } catch (err) {
      console.error('Failed to remove connection:', err);
    } finally {
      setRemoving(null);
    }
  };

  const handleSaveNative = async (entityId, overrides) => {
    if (overrides) {
      await saveNativeOverride(entityId, overrides);
      setNativeOverrides((prev) => ({ ...prev, [entityId]: overrides }));
    } else {
      setNativeOverrides((prev) => { const next = { ...prev }; delete next[entityId]; return next; });
    }
  };

  const handleConfirmMerge = useCallback(async (source, target, reason, mergeResolution) => {
    if (mergeResolution && Object.keys(mergeResolution).length > 0) {
      const merged = { ...(nativeOverrides[target.id] || {}), ...mergeResolution };
      await saveNativeOverride(target.id, merged);
      setNativeOverrides((prev) => ({ ...prev, [target.id]: { ...prev[target.id], ...mergeResolution } }));
    }
    const sourceRels = networkRelationships.filter((r) => r.source === source.id || r.target === source.id);
    const result = await createNativeMerge({
      sourceEntityId: source.id,
      targetEntityId: target.id,
      reason,
      migratedRelationships: sourceRels.map((r) => ({ source: r.source, target: r.target })),
    });
    return result.data;
  }, [nativeOverrides, networkRelationships]);

  const handleUndoMerge = useCallback(async (mergeId) => {
    await undoNativeMerge(mergeId);
  }, []);

  // Client-side network filter on API results
  const filtered = networkFilter === 'all'
    ? results
    : networkFilter === 'in'
      ? results.filter((e) => networkEntityIds.has(e.id))
      : results.filter((e) => !networkEntityIds.has(e.id));

  // Industry counts from current results
  const industryCounts = {};
  results.forEach((e) => {
    industryCounts[e.industry] = (industryCounts[e.industry] || 0) + 1;
  });

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4">
        <h1 className="text-xl font-normal mb-3" style={{ color: QB.textPrimary }}>Search Intuit Business Network</h1>
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: QB.textMuted }} />
          <input ref={inputRef} type="text" value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search businesses, industries, commodities..."
            className="w-full pl-10 pr-10 py-2.5 rounded border text-sm focus:outline-none focus:ring-2" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }} />
          {loading && <Loader2 size={16} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin" style={{ color: QB.textMuted }} />}
          {!loading && q && (
            <button onClick={() => setQ('')} className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-gray-100">
              <X size={14} style={{ color: QB.textMuted }} />
            </button>
          )}
        </div>
      </div>
      <div className="flex-1 flex min-h-0 px-6 pb-4 gap-4">
        <div className="w-48 space-y-3 shrink-0">
          <Widget title="NETWORK">
            <div className="space-y-0.5">
              {(() => {
                const inCount = results.filter((e) => networkEntityIds.has(e.id)).length;
                const outCount = results.length - inCount;
                return [
                  { k: 'all', l: 'All results', n: results.length },
                  { k: 'in', l: 'In my network', n: inCount },
                  { k: 'out', l: 'Not in network', n: outCount },
                ].map((f) => (
                  <button key={f.k} onClick={() => setNetworkFilter(f.k)}
                    className="w-full flex items-center gap-2 text-xs px-2 py-1.5 rounded transition-colors text-left"
                    style={{ backgroundColor: networkFilter === f.k ? QB.purpleLight : 'transparent', color: networkFilter === f.k ? QB.purpleDark : QB.textSecondary }}>
                    <span className="flex-1">{f.l}</span>
                    <span style={{ color: QB.textMuted }}>{f.n}</span>
                  </button>
                ));
              })()}
            </div>
          </Widget>
          <Widget title="INDUSTRY">
            <div className="space-y-0.5">
              {Object.entries(INDUSTRIES).slice(0, 8).map(([code, ind]) => {
                const cnt = industryCounts[code] || 0;
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
            <p className="text-xs" style={{ color: QB.textMuted }}>
              {searched
                ? <>Showing {filtered.length} results{q ? ` for "${q}"` : ''}{cached ? ' (cached)' : ''}</>
                : 'Type to search the Intuit Business Network'}
            </p>
            <div className="flex items-center gap-1 text-xs">
              <SortAsc size={12} style={{ color: QB.textMuted }} />
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="text-xs bg-transparent border-none focus:outline-none cursor-pointer" style={{ color: QB.textSecondary }}>
                <option value="relevance">Relevance</option><option value="volume">Volume</option><option value="connections">Connections</option><option value="confidence">Confidence</option>
              </select>
            </div>
          </div>
          {!searched && !loading && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Search size={32} style={{ color: QB.textMuted }} className="mb-3 opacity-40" />
              <p className="text-sm" style={{ color: QB.textMuted }}>Search across all businesses in the Intuit Business Network</p>
              <p className="text-xs mt-1" style={{ color: QB.textMuted }}>Find vendors, clients, and potential partners</p>
            </div>
          )}
          {filtered.map((ent) => {
            const ind = getIndustry(ent.industry);
            const inNetwork = networkEntityIds.has(ent.id);
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
                  <div className="flex items-center gap-2">
                    {!inNetwork && (
                      <span className="text-[9px] font-medium px-1.5 py-0.5 rounded" style={{ backgroundColor: QB.purpleLight, color: QB.purpleDark }}>not in network</span>
                    )}
                    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded" style={{ backgroundColor: ent.confidence >= 0.9 ? QB.greenLight : QB.orangeLight, color: ent.confidence >= 0.9 ? QB.greenDark : QB.orange }}>{Math.round(ent.confidence * 100)}%</span>
                  </div>
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
          {searched && filtered.length === 0 && !loading && (
            <div className="text-center py-12">
              <p className="text-sm" style={{ color: QB.textMuted }}>No results found{q ? ` for "${q}"` : ''}</p>
            </div>
          )}
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
              onAddConnection={(ent) => setAddTarget(ent)}
              onRemoveConnection={(ent) => handleRemoveConnection(null, ent)}
              isInNetwork={networkEntityIds.has(selectedEntity.id)}
              isDirectConnection={!!networkRelationships.find((r) => (r.source === selectedEntityId && r.target === selectedEntity.id) || (r.target === selectedEntityId && r.source === selectedEntity.id))}
              onMerge={() => setMergeSource(selectedEntity)}
              onSelectEntity={setSelectedEntity}
              vendorRels={networkRelationships.filter((r) => (r.source === selectedEntity.id || r.target === selectedEntity.id) && getRelType(r, selectedEntity.id) === 'vendor').sort((a, b) => b.volume - a.volume)}
              clientRels={networkRelationships.filter((r) => (r.source === selectedEntity.id || r.target === selectedEntity.id) && getRelType(r, selectedEntity.id) === 'client').sort((a, b) => b.volume - a.volume)}
              allEntities={results}
            />
          </div>
        )}
      </div>

      {addTarget && (
        <AddConnectionModal
          entity={addTarget}
          onConfirm={handleAddConnection}
          onClose={() => setAddTarget(null)}
        />
      )}

      {mergeSource && (
        <MergeFlowModal
          sourceEntity={mergeSource}
          allEntities={results}
          relationships={networkRelationships}
          onConfirmMerge={handleConfirmMerge}
          onUndoMerge={handleUndoMerge}
          onClose={() => setMergeSource(null)}
        />
      )}
    </div>
  );
}
