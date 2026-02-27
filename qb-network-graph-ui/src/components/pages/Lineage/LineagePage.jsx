import { useState, useEffect, useMemo } from 'react';
import { QB } from '@/constants/colors';
import { getEntityAuditTrail, getLineageEntities, getEntitySnapshot, restoreEntity } from '@/api/lineage';
import { getEntity } from '@/api/entities';
import { EntitySelector } from './components/EntitySelector';
import { TimeTravelSlider } from './components/TimeTravelSlider';
import { TimelineEntry } from './components/TimelineEntry';
import { EntitySnapshot } from './components/EntitySnapshot';

const DECISIONS = ['MERGE', 'NEW_ENTITY', 'REVIEW', 'NO_MERGE_FOUND', 'RESTORE'];
const DECISION_LABELS = { MERGE: 'Merged', NEW_ENTITY: 'Created', REVIEW: 'Review', NO_MERGE_FOUND: 'No match', RESTORE: 'Restored' };

const TRIGGERS = ['AI_AGENT_DETERMINISTIC', 'AI_AGENT_EMBEDDING', 'AI_AGENT_LLM', 'AI_AGENT_NEW', 'RE_EVALUATION', 'USER_ACTION'];
const TRIGGER_LABELS = { AI_AGENT_DETERMINISTIC: 'EIN match', AI_AGENT_EMBEDDING: 'Embedding', AI_AGENT_LLM: 'LLM', AI_AGENT_NEW: 'New entity', RE_EVALUATION: 'Re-eval', USER_ACTION: 'User action' };

export default function LineagePage({ selectedEntity }) {
  const [entities, setEntities] = useState([]);
  const [selectedEntityId, setSelectedEntityId] = useState(selectedEntity?.id || '1');
  const [entries, setEntries] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [snapshot, setSnapshot] = useState(null);

  // Filters — all checked by default
  const [decisionFilter, setDecisionFilter] = useState(new Set(DECISIONS));
  const [triggerFilter, setTriggerFilter] = useState(new Set(TRIGGERS));

  // Load entities list
  useEffect(() => {
    getLineageEntities().then((r) => setEntities(r.data));
  }, []);

  // Pre-select from AppLayout context
  useEffect(() => {
    if (selectedEntity?.id) setSelectedEntityId(selectedEntity.id);
  }, [selectedEntity?.id]);

  const [currentEntity, setCurrentEntity] = useState(null);

  // Load audit trail + current entity when entity changes
  useEffect(() => {
    if (!selectedEntityId) return;
    setExpandedId(null);
    setSelectedDate(null);
    setSnapshot(null);
    getEntityAuditTrail(selectedEntityId).then((r) => setEntries(r.data));
    getEntity(selectedEntityId).then((r) => setCurrentEntity(r.data)).catch(() => setCurrentEntity(null));
  }, [selectedEntityId]);

  // Load snapshot when time travel date changes
  useEffect(() => {
    if (!selectedDate || !selectedEntityId) {
      setSnapshot(null);
      return;
    }
    getEntitySnapshot(selectedEntityId, selectedDate).then((r) => setSnapshot(r.data));
  }, [selectedDate, selectedEntityId]);

  // Filter + date-capped entries
  const filteredEntries = useMemo(() => {
    return entries.filter((e) => {
      if (!decisionFilter.has(e.decision)) return false;
      if (!triggerFilter.has(e.trigger_type)) return false;
      if (selectedDate && new Date(e.created_at) > new Date(selectedDate)) return false;
      return true;
    });
  }, [entries, decisionFilter, triggerFilter, selectedDate]);

  // Stats
  const stats = useMemo(() => {
    const merges = filteredEntries.filter((e) => e.decision === 'MERGE').length;
    const avgConf = filteredEntries.length
      ? filteredEntries.reduce((s, e) => s + e.confidence, 0) / filteredEntries.length
      : 0;
    return { total: filteredEntries.length, merges, avgConf };
  }, [filteredEntries]);

  const toggleFilter = (set, setter, value) => {
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  };

  const [restoreEntry, setRestoreEntry] = useState(null);

  const handleRestore = (entry) => setRestoreEntry(entry);

  const [restoring, setRestoring] = useState(false);

  const confirmRestore = async () => {
    setRestoring(true);
    try {
      await restoreEntity(selectedEntityId, restoreEntry.audit_id, restoreEntry.golden_record_after);
      // Reload trail + current entity to reflect the restore
      const [trail, entity] = await Promise.all([
        getEntityAuditTrail(selectedEntityId),
        getEntity(selectedEntityId),
      ]);
      setEntries(trail.data);
      setCurrentEntity(entity.data);
    } catch (err) {
      console.error('Restore failed:', err);
    } finally {
      setRestoring(false);
      setRestoreEntry(null);
    }
  };

  const dateLabel = selectedDate
    ? new Date(selectedDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : 'Now';

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Page header */}
      <div className="px-6 pt-5 pb-3">
        <div className="flex items-center justify-between mb-1">
          <div>
            <h1 className="text-base font-semibold" style={{ color: QB.textPrimary }}>Connection lineage</h1>
            <p className="text-xs" style={{ color: QB.textMuted }}>
              Audit trail &amp; time travel for any golden record entity
            </p>
          </div>
          <EntitySelector
            entities={entities}
            selectedId={selectedEntityId}
            onSelect={setSelectedEntityId}
          />
        </div>
      </div>

      {/* Time travel slider */}
      <div className="px-6 pb-3">
        <TimeTravelSlider
          entries={entries}
          selectedDate={selectedDate}
          onChange={setSelectedDate}
          filteredCount={filteredEntries.length}
        />
      </div>

      {/* 3-column layout */}
      <div className="flex-1 flex min-h-0 px-6 pb-4 gap-4">
        {/* LEFT — Filters */}
        <div className="w-44 shrink-0 overflow-y-auto">
          <div className="rounded-lg p-3" style={{ backgroundColor: QB.cardBg, border: '1px solid ' + QB.cardBorder }}>
            {/* Decision filters */}
            <div className="text-[10px] font-semibold tracking-wider mb-2" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
              DECISION
            </div>
            {DECISIONS.map((d) => (
              <label key={d} className="flex items-center gap-2 text-xs py-0.5 cursor-pointer" style={{ color: QB.textSecondary }}>
                <input
                  type="checkbox"
                  checked={decisionFilter.has(d)}
                  onChange={() => toggleFilter(decisionFilter, setDecisionFilter, d)}
                  className="rounded"
                />
                {DECISION_LABELS[d]}
              </label>
            ))}

            {/* Trigger filters */}
            <div className="text-[10px] font-semibold tracking-wider mt-4 mb-2" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
              TRIGGER
            </div>
            {TRIGGERS.map((t) => (
              <label key={t} className="flex items-center gap-2 text-xs py-0.5 cursor-pointer" style={{ color: QB.textSecondary }}>
                <input
                  type="checkbox"
                  checked={triggerFilter.has(t)}
                  onChange={() => toggleFilter(triggerFilter, setTriggerFilter, t)}
                  className="rounded"
                />
                {TRIGGER_LABELS[t]}
              </label>
            ))}

            {/* Stats */}
            <div className="border-t mt-4 pt-3" style={{ borderColor: QB.cardBorder }}>
              <div className="text-[10px] font-semibold tracking-wider mb-2" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
                STATS
              </div>
              <div className="space-y-1 text-xs" style={{ color: QB.textSecondary }}>
                <div>{stats.total} events</div>
                <div>{stats.merges} merges</div>
                <div>avg {Math.round(stats.avgConf * 100)}%</div>
              </div>
            </div>
          </div>
        </div>

        {/* CENTER — Timeline */}
        <div className="flex-1 min-w-0 overflow-y-auto pr-1">
          {filteredEntries.length === 0 ? (
            <div className="flex items-center justify-center h-40 text-sm" style={{ color: QB.textMuted }}>
              {entries.length === 0 ? 'Select an entity to view its audit trail' : 'No events match the current filters'}
            </div>
          ) : (
            filteredEntries.map((entry, i) => (
              <TimelineEntry
                key={entry.audit_id}
                entry={entry}
                isExpanded={expandedId === entry.audit_id}
                onToggle={() => setExpandedId(expandedId === entry.audit_id ? null : entry.audit_id)}
                onRestore={handleRestore}
                isFirst={i === 0}
                isLast={i === filteredEntries.length - 1}
              />
            ))
          )}
        </div>

        {/* RIGHT — Snapshot */}
        <div className="w-56 shrink-0 overflow-y-auto">
          {snapshot ? (
            <EntitySnapshot entity={snapshot} dateLabel={dateLabel} />
          ) : currentEntity ? (
            <EntitySnapshot entity={currentEntity} dateLabel="Current" />
          ) : (
            <div
              className="rounded-lg p-4 text-center text-xs"
              style={{ backgroundColor: QB.cardBg, border: '1px solid ' + QB.cardBorder, color: QB.textMuted }}
            >
              {selectedDate
                ? 'No connection state available at this date'
                : 'Select a connection to view its current state'}
            </div>
          )}
        </div>
      </div>

      {/* Restore confirmation modal */}
      {restoreEntry && (
        <>
          <div className="fixed inset-0 bg-black/30 z-50" onClick={() => setRestoreEntry(null)} />
          <div
            className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-96 rounded-lg shadow-xl p-5"
            style={{ backgroundColor: QB.cardBg }}
          >
            <h3 className="text-sm font-semibold mb-2" style={{ color: QB.textPrimary }}>
              Restore entity state?
            </h3>
            <p className="text-xs mb-1" style={{ color: QB.textSecondary }}>
              This will revert the golden record to its state as of:
            </p>
            <p className="text-xs font-medium mb-3" style={{ color: QB.purple }}>
              {new Date(restoreEntry.created_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
            </p>
            <p className="text-[11px] mb-4 px-2.5 py-2 rounded" style={{ backgroundColor: QB.orangeLight, color: QB.orange }}>
              All changes made after this point will be undone. This action creates a new audit entry and can be reversed.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setRestoreEntry(null)}
                className="flex-1 text-xs py-2 rounded border transition-colors hover:bg-gray-50"
                style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}
              >
                Cancel
              </button>
              <button
                onClick={confirmRestore}
                disabled={restoring}
                className="flex-1 text-xs py-2 rounded text-white transition-colors hover:opacity-90 disabled:opacity-50"
                style={{ backgroundColor: QB.purple }}
              >
                {restoring ? 'Restoring...' : 'Restore'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
