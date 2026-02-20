import { useState, useCallback, useMemo } from 'react';
import { Eye, EyeOff, X, Navigation, User, Globe } from 'lucide-react';
import { BarChart, Bar, XAxis, ResponsiveContainer, Cell } from 'recharts';
import { QB } from '@/constants/colors';
import { PERSPECTIVE } from '@/constants/perspective';
import { findPath } from '@/utils/graph';
import { getNativeFields } from '@/utils/perspective';
import { ENTITIES, RELATIONSHIPS, MONTHLY_VOLUME, NATIVE_OVERRIDES, NATIVE_MERGES } from '@/api/mock/data';
import { saveNativeOverride, createNativeMerge, undoNativeMerge } from '@/api/native';
import { Widget, EntityDetailPanel, MergeFlowModal } from '@/components/shared';
import { NetworkGraph } from './components/NetworkGraph';

export default function NetworkPage({ selectedEntity, onSelect, onOpenAI, privacy }) {
  const [depth, setDepth] = useState(2);
  const [edgeFilter, setEdgeFilter] = useState('all');
  const [showDormant, setShowDormant] = useState(true);
  const [pathMode, setPathMode] = useState(false);
  const [pathStart, setPathStart] = useState(null);
  const [pathEnd, setPathEnd] = useState(null);
  const [pathResult, setPathResult] = useState(null);
  const [nativeOverrides, setNativeOverrides] = useState(NATIVE_OVERRIDES);
  const [nativeMerges, setNativeMerges] = useState(NATIVE_MERGES);
  const [mergeSource, setMergeSource] = useState(null);
  const [perspective, setPerspective] = useState(PERSPECTIVE.NATIVE);

  const isNativeView = perspective === PERSPECTIVE.NATIVE;

  // When viewing Network perspective, strip all native overlays
  const activeOverrides = isNativeView ? nativeOverrides : {};
  const activeMerges = isNativeView ? nativeMerges : [];

  const nativeOverride = selectedEntity ? (activeOverrides[selectedEntity.id] || null) : null;

  // Count native modifications for the toggle label
  const nativeCount = useMemo(() => {
    const overrideCount = Object.keys(nativeOverrides).length;
    const mergeCount = nativeMerges.length;
    return overrideCount + mergeCount;
  }, [nativeOverrides, nativeMerges]);

  const handleSaveNative = useCallback(async (entityId, overrides) => {
    if (overrides) {
      await saveNativeOverride(entityId, overrides);
      setNativeOverrides((prev) => ({ ...prev, [entityId]: overrides }));
    } else {
      setNativeOverrides((prev) => { const next = { ...prev }; delete next[entityId]; return next; });
    }
  }, []);

  const handleConfirmMerge = useCallback(async (source, target, reason, mergeResolution) => {
    // Apply per-field resolution as native overrides on the surviving entity
    if (mergeResolution && Object.keys(mergeResolution).length > 0) {
      const merged = { ...(nativeOverrides[target.id] || {}), ...mergeResolution };
      await saveNativeOverride(target.id, merged);
      setNativeOverrides((prev) => ({ ...prev, [target.id]: { ...prev[target.id], ...mergeResolution } }));
    }
    const sourceRels = RELATIONSHIPS.filter((r) => r.source === source.id || r.target === source.id);
    const result = await createNativeMerge({
      sourceEntityId: source.id,
      targetEntityId: target.id,
      reason,
      migratedRelationships: sourceRels.map((r) => ({ source: r.source, target: r.target })),
    });
    return result.data;
  }, [nativeOverrides]);

  const handleUndoMerge = useCallback(async (mergeId) => {
    await undoNativeMerge(mergeId);
  }, []);

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
          <span className="text-[1px]" style={{ color: QB.cardBorder }}>|</span>
          <div className="flex border rounded" style={{ borderColor: isNativeView ? QB.purple + '50' : QB.cardBorder }}>
            <button
              onClick={() => setPerspective(PERSPECTIVE.NATIVE)}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs transition-colors"
              style={{
                backgroundColor: isNativeView ? QB.purple : 'white',
                color: isNativeView ? 'white' : QB.textSecondary,
                borderRight: '1px solid ' + (isNativeView ? QB.purple : QB.cardBorder),
              }}
            >
              <User size={10} /> My View
              {isNativeView && nativeCount > 0 && (
                <span className="text-[9px] px-1 rounded-full" style={{ backgroundColor: 'rgba(255,255,255,0.25)' }}>
                  {nativeCount}
                </span>
              )}
            </button>
            <button
              onClick={() => setPerspective(PERSPECTIVE.GLOBAL)}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs transition-colors"
              style={{
                backgroundColor: !isNativeView ? QB.link : 'white',
                color: !isNativeView ? 'white' : QB.textSecondary,
              }}
            >
              <Globe size={10} /> Network
            </button>
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
            edgeFilter={edgeFilter} showDormant={showDormant} privacy={privacy}
            nativeOverrides={activeOverrides} nativeMerges={activeMerges} />
        </div>

        {selectedEntity && (
          <div className="w-80 flex flex-col gap-3 overflow-y-auto">
            <EntityDetailPanel
              globalEntity={selectedEntity}
              nativeOverride={nativeOverride}
              onSaveNative={handleSaveNative}
              onOpenAI={onOpenAI}
              onMerge={() => setMergeSource(selectedEntity)}
              onSelectEntity={onSelect}
              vendorRels={vendorRels}
              clientRels={clientRels}
              allEntities={ENTITIES}
            />

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
          </div>
        )}
      </div>

      {/* Merge flow modal */}
      {mergeSource && (
        <MergeFlowModal
          sourceEntity={mergeSource}
          allEntities={ENTITIES}
          relationships={RELATIONSHIPS}
          onConfirmMerge={handleConfirmMerge}
          onUndoMerge={handleUndoMerge}
          onClose={() => setMergeSource(null)}
        />
      )}
    </div>
  );
}
