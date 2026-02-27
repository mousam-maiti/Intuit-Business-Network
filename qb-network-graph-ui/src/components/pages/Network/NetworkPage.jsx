import { useState, useEffect, useCallback, useMemo } from 'react';
import { X, Navigation, Plus } from 'lucide-react';
import { BarChart, Bar, XAxis, ResponsiveContainer, Cell } from 'recharts';
import { QB } from '@/constants/colors';
import { findPath } from '@/utils/graph';
import { getEntities } from '@/api/entities';
import { getAllRelationships, getMonthlyVolume } from '@/api/relationships';
import { getNativeOverrides, getNativeMerges } from '@/api/native';
import { saveNativeOverride, createNativeMerge, undoNativeMerge } from '@/api/native';
import { Widget, EntityDetailPanel, MergeFlowModal, AddConnectionModal } from '@/components/shared';
import { NetworkGraph } from './components/NetworkGraph';
export default function NetworkPage({ selectedEntity, onSelect, onOpenAI }) {
  const [depth, setDepth] = useState(2);
  const [panelOpen, setPanelOpen] = useState(false);
  const [edgeFilter, setEdgeFilter] = useState('all');
  const [pathMode, setPathMode] = useState(false);
  const [pathStart, setPathStart] = useState(null);
  const [pathEnd, setPathEnd] = useState(null);
  const [pathResult, setPathResult] = useState(null);
  const [nativeOverrides, setNativeOverrides] = useState({});
  const [nativeMerges, setNativeMerges] = useState([]);
  const [mergeSource, setMergeSource] = useState(null);
  const [showAddConn, setShowAddConn] = useState(false);

  const [allEntities, setAllEntities] = useState([]);
  const [allRelationships, setAllRelationships] = useState([]);
  const [volumeData, setVolumeData] = useState([]);

  useEffect(() => {
    getEntities().then(r => setAllEntities(r.data));
    getAllRelationships().then(r => setAllRelationships(r.data));
    getNativeOverrides().then(r => setNativeOverrides(r.data));
    getNativeMerges().then(r => setNativeMerges(r.data));
  }, []);

  useEffect(() => {
    if (selectedEntity?.id) {
      getMonthlyVolume(selectedEntity.id).then(r => setVolumeData(r.data));
    }
  }, [selectedEntity?.id]);

  const nativeOverride = selectedEntity ? (nativeOverrides[selectedEntity.id] || null) : null;

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
    const sourceRels = allRelationships.filter((r) => r.source === source.id || r.target === source.id);
    const result = await createNativeMerge({
      sourceEntityId: source.id,
      targetEntityId: target.id,
      reason,
      migratedRelationships: sourceRels.map((r) => ({ source: r.source, target: r.target })),
    });
    return result.data;
  }, [nativeOverrides, allRelationships]);

  const handleUndoMerge = useCallback(async (mergeId) => {
    await undoNativeMerge(mergeId);
  }, []);

  const handlePathSelect = useCallback((id) => {
    if (!pathStart) {
      setPathStart(id); setPathEnd(null); setPathResult(null);
    } else if (id !== pathStart) {
      setPathEnd(id);
      setPathResult(findPath(allRelationships, pathStart, id));
    }
  }, [pathStart]);

  const clearPath = () => { setPathMode(false); setPathStart(null); setPathEnd(null); setPathResult(null); };

  const handleSelect = useCallback((entity) => {
    onSelect(entity);
    setPanelOpen(true);
  }, [onSelect]);

  const rels = selectedEntity ? allRelationships.filter((r) => r.source === selectedEntity.id || r.target === selectedEntity.id).sort((a, b) => b.volume - a.volume) : [];
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
          <button onClick={() => pathMode ? clearPath() : setPathMode(true)}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded transition-colors"
            style={{ backgroundColor: pathMode ? QB.orange + '15' : 'white', color: pathMode ? QB.orange : QB.textSecondary, border: '1px solid ' + (pathMode ? QB.orange + '50' : QB.cardBorder) }}>
            <Navigation size={12} /> {pathMode ? 'Exit path mode' : 'Find path'}
          </button>
          <span className="text-[1px]" style={{ color: QB.cardBorder }}>|</span>
          <span style={{ color: QB.textMuted }}>Depth:</span>
          <div className="flex border rounded" style={{ borderColor: QB.cardBorder }}>
            {[{ d: 1, c: QB.purple }, { d: 2, c: QB.orange }].map(({ d, c }) => (
              <button key={d} onClick={() => setDepth(d)} className="px-3 py-1.5 text-xs transition-colors"
                style={{ backgroundColor: depth === d ? c : 'white', color: depth === d ? 'white' : QB.textSecondary, borderRight: d < 2 ? '1px solid ' + QB.cardBorder : 'none' }}>
                {d}-hop
              </button>
            ))}
          </div>
          <span className="text-[1px]" style={{ color: QB.cardBorder }}>|</span>
          <button onClick={() => setShowAddConn(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white" style={{ backgroundColor: QB.green }}>
            <Plus size={12} /> Add connection
          </button>
        </div>
      </div>

      {/* Path mode banner */}
      {pathMode && (
        <div className="mx-6 mb-2 flex items-center gap-3 px-4 py-2 rounded text-xs" style={{ backgroundColor: QB.orange + '10', border: '1px solid ' + QB.orange + '30', color: QB.orange }}>
          <Navigation size={13} />
          <span className="flex-1">
            {!pathStart ? 'Click a starting entity on the graph' :
              !pathEnd ? (<>Start: <strong>{allEntities.find((e) => e.id === pathStart)?.name}</strong> &mdash; Now click the destination</>) :
                pathResult ? (<>Path: {pathResult.map((id, i) => (<span key={id}>{i > 0 && ' \u2192 '}<strong>{allEntities.find((e) => e.id === id)?.name}</strong></span>))} <span style={{ color: QB.textMuted }}>&middot; {pathResult.length - 1} hop{pathResult.length > 2 ? 's' : ''} &middot; BFS &lt;30ms</span></>) :
                  <span style={{ color: QB.red }}>No path found between these entities</span>}
          </span>
          {pathResult && <button onClick={() => { setPathStart(null); setPathEnd(null); setPathResult(null); }} className="text-[10px] px-2 py-1 rounded" style={{ backgroundColor: QB.orange + '20' }}>Reset</button>}
          <button onClick={clearPath} className="p-0.5"><X size={13} /></button>
        </div>
      )}

      {/* Graph + sidebar */}
      <div className="flex-1 flex min-h-0 px-6 pb-4 gap-4">
        <div className="flex-1">
          <NetworkGraph selectedId={selectedEntity?.id} onSelect={handleSelect} depth={depth}
            pathNodes={pathResult} pathMode={pathMode} onPathSelect={handlePathSelect}
            edgeFilter={edgeFilter} showDormant={true}
            nativeOverrides={nativeOverrides} nativeMerges={nativeMerges}
            allEntities={allEntities} allRelationships={allRelationships} />
        </div>

        {selectedEntity && panelOpen && (
          <div className="w-80 flex flex-col gap-3 overflow-y-auto">
            <div className="flex justify-end">
              <button onClick={() => setPanelOpen(false)} className="p-1 rounded hover:bg-gray-100 transition-colors">
                <X size={14} style={{ color: QB.textMuted }} />
              </button>
            </div>
            <EntityDetailPanel
              globalEntity={selectedEntity}
              nativeOverride={nativeOverride}
              onSaveNative={handleSaveNative}
              onOpenAI={onOpenAI}
              onMerge={() => setMergeSource(selectedEntity)}
              onSelectEntity={onSelect}
              vendorRels={vendorRels}
              clientRels={clientRels}
              allEntities={allEntities}
            />

            <div className="flex gap-3">
              <Widget title="MATCH SCORE">
                <div className="flex items-center justify-center h-20">
                  <svg width="72" height="72" viewBox="0 0 72 72">
                    <circle cx="36" cy="36" r="28" fill="none" stroke="#F0F1F3" strokeWidth="6" />
                    <circle cx="36" cy="36" r="28" fill="none"
                      stroke={selectedEntity.confidence >= 0.9 ? QB.green : QB.orange}
                      strokeWidth="6" strokeLinecap="round"
                      strokeDasharray={`${2 * Math.PI * 28 * (selectedEntity.confidence || 0)} ${2 * Math.PI * 28}`}
                      transform="rotate(-90 36 36)" />
                    <text x="36" y="34" textAnchor="middle" fill={QB.textPrimary} fontSize="14" fontWeight="600" fontFamily="system-ui">
                      {Math.round((selectedEntity.confidence || 0) * 100)}%
                    </text>
                    <text x="36" y="46" textAnchor="middle" fill={QB.textMuted} fontSize="8" fontFamily="system-ui">
                      confidence
                    </text>
                  </svg>
                </div>
              </Widget>
              <div className="flex-1">
                <Widget title="TRANSACTION VOLUME">
                  <div className="h-20">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={volumeData}>
                        <XAxis dataKey="month" tick={{ fontSize: 9, fill: QB.textMuted }} axisLine={false} tickLine={false} />
                        <Bar dataKey="vol" radius={[2, 2, 0, 0]}>
                          {volumeData.map((_, i) => <Cell key={i} fill={i % 2 === 0 ? QB.green : QB.purple} />)}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </Widget>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Merge flow modal */}
      {mergeSource && (
        <MergeFlowModal
          sourceEntity={mergeSource}
          allEntities={allEntities}
          relationships={allRelationships}
          onConfirmMerge={handleConfirmMerge}
          onUndoMerge={handleUndoMerge}
          onClose={() => setMergeSource(null)}
        />
      )}

      <AddConnectionModal open={showAddConn} onClose={() => setShowAddConn(false)} />
    </div>
  );
}
