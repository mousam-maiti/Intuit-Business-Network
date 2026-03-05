import { useState, useEffect, useCallback } from 'react';
import {
  Plus, Check, Zap, Building2,
  UserPlus, Receipt, Activity, Layers, Target,
} from 'lucide-react';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { getRelType } from '@/utils/graph';
import { getEntities } from '@/api/entities';
import { getAllRelationships } from '@/api/relationships';
import { getAutoDetected, getManualConnections } from '@/api/connections';
import { getNativeOverrides, saveNativeOverride, createNativeMerge, undoNativeMerge } from '@/api/native';
import { Widget, RelTypeBadge, EntityDetailPanel, MergeFlowModal, AddConnectionModal } from '@/components/shared';

export default function ConnectionsPage({ onNavigate }) {
  const [autoConns, setAutoConns] = useState([]);
  const [manualConns, setManualConns] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [nativeOverrides, setNativeOverrides] = useState({});
  const [mergeSource, setMergeSource] = useState(null);
  const [allEntities, setAllEntities] = useState([]);
  const [allRelationships, setAllRelationships] = useState([]);

  useEffect(() => {
    getAutoDetected().then(r => setAutoConns(r.data));
    getManualConnections().then(r => setManualConns(r.data));
    getNativeOverrides().then(r => setNativeOverrides(r.data));
    getEntities().then(r => setAllEntities(r.data));
    getAllRelationships().then(r => setAllRelationships(r.data));
  }, []);

  const handleSaveNative = useCallback(async (entityId, overrides) => {
    if (overrides) {
      await saveNativeOverride(entityId, overrides);
      setNativeOverrides((prev) => ({ ...prev, [entityId]: overrides }));
    } else {
      setNativeOverrides((prev) => { const next = { ...prev }; delete next[entityId]; return next; });
    }
  }, []);

  const handleConfirmMerge = useCallback(async (source, target, reason, mergeResolution) => {
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

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-6 py-4">
        <div>
          <h1 className="text-xl font-normal" style={{ color: QB.textPrimary }}>Connections</h1>
          <p className="text-xs mt-1" style={{ color: QB.textMuted }}>Connections are auto-detected from your QuickBooks invoices, bills, and payments via CDC pipeline.</p>
        </div>
        <button onClick={() => setShowModal(true)} className="flex items-center gap-1.5 px-4 py-2 rounded text-sm font-medium text-white shrink-0" style={{ backgroundColor: QB.green }}>
          <Plus size={14} /> Add connection
        </button>
      </div>
      <div className="flex-1 flex min-h-0 px-6 pb-4 gap-4">
        <div className="flex-1 overflow-y-auto space-y-5">

          {/* ── SECTION 1: Auto-detected connections ── */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full flex items-center justify-center" style={{ backgroundColor: QB.greenLight }}>
                <Zap size={12} style={{ color: QB.green }} />
              </div>
              <span className="text-sm font-medium" style={{ color: QB.textPrimary }}>Auto-detected from your books</span>
              <span className="text-xs" style={{ color: QB.textMuted }}>{"\u2014"} Tier 1 deterministic match, linked automatically</span>
            </div>

            <Widget>
              {/* Pipeline explainer */}
              <div className="flex items-center gap-6 py-2.5 px-3 rounded mb-3 text-[10px]" style={{ backgroundColor: "#F9FAFB", color: QB.textMuted }}>
                <span className="flex items-center gap-1"><Receipt size={10} /> QB invoice/bill</span>
                <span>{"\u2192"}</span>
                <span className="flex items-center gap-1"><Activity size={10} /> CDC binlog</span>
                <span>{"\u2192"}</span>
                <span className="flex items-center gap-1"><Layers size={10} /> Flink normalize</span>
                <span>{"\u2192"}</span>
                <span className="flex items-center gap-1"><Target size={10} /> Entity resolve</span>
                <span>{"\u2192"}</span>
                <span className="flex items-center gap-1" style={{ color: QB.green }}><Check size={10} /> Graph edge</span>
              </div>

              <div className="space-y-1">
                {autoConns.map(ac => {
                  const ind = getIndustry(ac.entity.industry);
                  return (
                    <div key={ac.id} className="flex items-center gap-3 py-2.5 border-b cursor-pointer hover:bg-gray-50 -mx-1 px-1 rounded"
                      style={{ borderColor: "#F0F0F0", backgroundColor: selectedEntity?.id === ac.entity.id ? '#F4F5F7' : undefined }}
                      onClick={() => setSelectedEntity(ac.entity)}>
                      <div className="w-8 h-8 rounded flex items-center justify-center shrink-0" style={{ backgroundColor: ind.color + "12" }}>
                        <Building2 size={14} style={{ color: ind.color }} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium" style={{ color: QB.textPrimary }}>{ac.entity.name}</span>
                          <RelTypeBadge type={ac.type} />
                        </div>
                        <div className="text-[11px]" style={{ color: QB.textMuted }}>
                          from {ac.source} ({ac.sourceDate}) {"\u00B7"} {ind.label} {"\u00B7"} {ac.entity.city}, {ac.entity.state}
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="flex items-center gap-1 text-[10px] font-medium" style={{ color: QB.green }}>
                          <Check size={10} /> {Math.round(ac.confidence * 100)}% match
                        </div>
                        <div className="text-[10px]" style={{ color: QB.textMuted }}>Tier 1 {"\u00B7"} {ac.latency} {"\u00B7"} {ac.time}</div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="text-center pt-3">
                <span className="text-[10px]" style={{ color: QB.textMuted }}>
                  {autoConns.length} connections auto-detected in the last 7 days {"\u00B7"} 68 total this month
                </span>
              </div>
            </Widget>
          </div>

          {/* ── SECTION 2: Manually added connections ── */}
          {manualConns.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-full flex items-center justify-center" style={{ backgroundColor: QB.purpleLight }}>
                  <UserPlus size={12} style={{ color: QB.purple }} />
                </div>
                <span className="text-sm font-medium" style={{ color: QB.textPrimary }}>Manually added</span>
                <span className="text-xs" style={{ color: QB.textMuted }}>{"\u2014"} Added via the connection form</span>
              </div>

              <Widget>
                <div className="space-y-1">
                  {manualConns.map(mc => {
                    const ind = getIndustry(mc.entity.industry);
                    return (
                      <div key={mc.id} className="flex items-center gap-3 py-2.5 border-b cursor-pointer hover:bg-gray-50 -mx-1 px-1 rounded"
                        style={{ borderColor: "#F0F0F0", backgroundColor: selectedEntity?.id === mc.entity.id ? '#F4F5F7' : undefined }}
                        onClick={() => setSelectedEntity(mc.entity)}>
                        <div className="w-8 h-8 rounded flex items-center justify-center shrink-0" style={{ backgroundColor: ind.color + "12" }}>
                          <Building2 size={14} style={{ color: ind.color }} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium" style={{ color: QB.textPrimary }}>{mc.entity.name}</span>
                            <RelTypeBadge type={mc.type} />
                          </div>
                          <div className="text-[11px]" style={{ color: QB.textMuted }}>
                            {mc.addedVia} {"\u00B7"} {ind.label} {"\u00B7"} {mc.entity.city}, {mc.entity.state}
                          </div>
                        </div>
                        <div className="text-right shrink-0">
                          <div className="text-[10px]" style={{ color: QB.purple }}>
                            <UserPlus size={10} className="inline mr-0.5" style={{ verticalAlign: "-1px" }} /> Manual
                          </div>
                          <div className="text-[10px]" style={{ color: QB.textMuted }}>{mc.time}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Widget>
            </div>
          )}

          <AddConnectionModal
            open={showModal}
            onClose={() => setShowModal(false)}
            onConnectionAdded={conn => setManualConns(prev => [conn, ...prev])}
          />

        </div>

        {/* Entity details panel */}
        {selectedEntity && (
          <div className="w-80 flex flex-col gap-3 overflow-y-auto shrink-0">
            <EntityDetailPanel
              globalEntity={selectedEntity}
              nativeOverride={nativeOverrides[selectedEntity.id] || null}
              onSaveNative={handleSaveNative}
              onOpenAI={() => onNavigate('assist', selectedEntity)}
              onMerge={() => setMergeSource(selectedEntity)}
              onSelectEntity={setSelectedEntity}
              vendorRels={allRelationships.filter((r) => (r.source === selectedEntity.id || r.target === selectedEntity.id) && getRelType(r, selectedEntity.id) === 'vendor').sort((a, b) => b.volume - a.volume)}
              clientRels={allRelationships.filter((r) => (r.source === selectedEntity.id || r.target === selectedEntity.id) && getRelType(r, selectedEntity.id) === 'client').sort((a, b) => b.volume - a.volume)}
              allEntities={allEntities}
            />
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
    </div>
  );
}
