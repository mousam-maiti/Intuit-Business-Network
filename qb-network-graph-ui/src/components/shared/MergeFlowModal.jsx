import { useState, useEffect, useMemo } from 'react';
import {
  X, Search, Building2, GitMerge, ArrowRight, Check, ChevronLeft,
  AlertTriangle, Undo2, Sparkles, Users,
} from 'lucide-react';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { fmt } from '@/utils/format';
import { MERGE_ORIGIN, NATIVE_EDITABLE_FIELDS } from '@/constants/perspective';
import { ScoreBar } from './ScoreBar';

// ── Step 1: Search & Select ─────────────────────────────

function MergeSearch({ sourceEntity, allEntities, relationships, onSelect, onCancel }) {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);

  // Compute suggested matches: entities in the same industry, excluding the source
  const suggestions = useMemo(() => {
    return allEntities
      .filter((e) => e.id !== sourceEntity.id)
      .map((e) => {
        // Simple similarity scoring for mock purposes
        let score = 0;
        if (e.industry === sourceEntity.industry) score += 0.3;
        if (e.city === sourceEntity.city) score += 0.2;
        if (e.state === sourceEntity.state) score += 0.1;
        const sharedCommodities = (e.commodities || []).filter((c) =>
          (sourceEntity.commodities || []).includes(c)
        );
        score += sharedCommodities.length * 0.1;
        // Name similarity (very rough)
        const srcWords = sourceEntity.name.toLowerCase().split(/\s+/);
        const tgtWords = e.name.toLowerCase().split(/\s+/);
        const sharedWords = srcWords.filter((w) => tgtWords.includes(w));
        score += sharedWords.length * 0.15;
        return { entity: e, score: Math.min(score, 0.99) };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, 5);
  }, [sourceEntity, allEntities]);

  // Filter by search query
  const results = useMemo(() => {
    if (!query.trim()) return suggestions;
    const q = query.toLowerCase();
    return allEntities
      .filter((e) => e.id !== sourceEntity.id)
      .filter((e) =>
        e.name.toLowerCase().includes(q) ||
        (e.variants || []).some((v) => v.toLowerCase().includes(q)) ||
        (e.commodities || []).some((c) => c.toLowerCase().includes(q))
      )
      .map((e) => {
        const match = suggestions.find((s) => s.entity.id === e.id);
        return { entity: e, score: match?.score || 0.1 };
      })
      .sort((a, b) => b.score - a.score);
  }, [query, sourceEntity, allEntities, suggestions]);

  // Shared neighbors between source and a candidate
  const getSharedNeighbors = (candidateId) => {
    const sourceNeighbors = new Set(
      relationships
        .filter((r) => r.source === sourceEntity.id || r.target === sourceEntity.id)
        .map((r) => (r.source === sourceEntity.id ? r.target : r.source))
    );
    const candidateNeighbors = relationships
      .filter((r) => r.source === candidateId || r.target === candidateId)
      .map((r) => (r.source === candidateId ? r.target : r.source));
    return candidateNeighbors.filter((n) => sourceNeighbors.has(n));
  };

  const sourceInd = getIndustry(sourceEntity.industry);

  return (
    <>
      {/* Source entity context */}
      <div className="px-6 py-3 border-b" style={{ borderColor: QB.cardBorder, backgroundColor: '#FAFAFA' }}>
        <div className="text-[10px] font-semibold tracking-wider mb-2" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
          MERGING
        </div>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded flex items-center justify-center" style={{ backgroundColor: sourceInd.color + '15' }}>
            <Building2 size={14} style={{ color: sourceInd.color }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium" style={{ color: QB.textPrimary }}>{sourceEntity.name}</div>
            <div className="text-[10px]" style={{ color: QB.textMuted }}>
              {sourceInd.label} &middot; {sourceEntity.city}, {sourceEntity.state} &middot; {sourceEntity.vendors + sourceEntity.clients} connections
            </div>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="px-6 pt-4 pb-3">
        <div className="text-[10px] mb-2" style={{ color: QB.purple }}>
          This merge applies to YOUR network view only.
        </div>
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: QB.textMuted }} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search entities to merge into..."
            autoFocus
            className="w-full pl-9 pr-3 py-2.5 rounded border text-sm focus:outline-none"
            style={{ borderColor: QB.cardBorder, color: QB.textPrimary }}
          />
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto px-6 pb-4">
        <div className="text-[10px] font-semibold tracking-wider mb-2" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
          {query.trim() ? 'SEARCH RESULTS' : 'SUGGESTED MATCHES'}
        </div>

        <div className="space-y-1.5">
          {results.map(({ entity: e, score }) => {
            const ind = getIndustry(e.industry);
            const shared = getSharedNeighbors(e.id);
            const isSelected = selected?.id === e.id;
            return (
              <div
                key={e.id}
                className="p-3 rounded border cursor-pointer transition-all"
                style={{
                  borderColor: isSelected ? QB.purple + '60' : QB.cardBorder,
                  backgroundColor: isSelected ? QB.purpleLight + '20' : 'white',
                }}
                onClick={() => setSelected(e)}
              >
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded flex items-center justify-center shrink-0" style={{ backgroundColor: ind.color + '12' }}>
                    <Building2 size={12} style={{ color: ind.color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium" style={{ color: QB.textPrimary }}>{e.name}</div>
                    <div className="text-[10px]" style={{ color: QB.textMuted }}>
                      {ind.label} &middot; {e.city}, {e.state}
                    </div>
                  </div>
                  <span
                    className="text-xs font-bold shrink-0"
                    style={{ color: score >= 0.5 ? QB.green : score >= 0.3 ? QB.orange : QB.textMuted }}
                  >
                    {Math.round(score * 100)}%
                  </span>
                </div>

                {/* Shared neighbors hint */}
                {shared.length > 0 && (
                  <div className="flex items-center gap-1 mt-1.5 text-[10px]" style={{ color: QB.textMuted }}>
                    <Users size={9} />
                    <span>{shared.length} shared neighbor{shared.length > 1 ? 's' : ''}</span>
                  </div>
                )}

                {/* Expand if selected */}
                {isSelected && (
                  <div className="mt-2.5 pt-2.5 border-t" style={{ borderColor: QB.cardBorder }}>
                    <div className="grid grid-cols-3 gap-2 mb-2.5 text-center">
                      {[
                        { l: 'Vendors', v: e.vendors, c: QB.purple },
                        { l: 'Clients', v: e.clients, c: QB.green },
                        { l: 'Volume', v: fmt(e.volume), c: QB.link },
                      ].map((s, i) => (
                        <div key={i} className="py-1.5 rounded" style={{ backgroundColor: '#F4F5F7' }}>
                          <div className="text-xs font-semibold" style={{ color: s.c }}>{s.v}</div>
                          <div className="text-[9px]" style={{ color: QB.textMuted }}>{s.l}</div>
                        </div>
                      ))}
                    </div>
                    <button
                      onClick={(ev) => { ev.stopPropagation(); onSelect(e); }}
                      className="w-full py-2 rounded text-xs font-medium text-white flex items-center justify-center gap-1.5"
                      style={{ backgroundColor: QB.purple }}
                    >
                      <ArrowRight size={12} /> Compare & merge
                    </button>
                  </div>
                )}
              </div>
            );
          })}

          {results.length === 0 && (
            <div className="text-center py-8 text-xs" style={{ color: QB.textMuted }}>
              No entities found{query.trim() ? ` matching "${query}"` : ''}.
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ── Step 2: Compare & Confirm (per-field resolution) ────

function MergeCompare({ sourceEntity, targetEntity, relationships, allEntities, onConfirm, onBack }) {
  const [reason, setReason] = useState('');
  const sourceInd = getIndustry(sourceEntity.industry);
  const targetInd = getIndustry(targetEntity.industry);

  // Human-readable labels for field keys
  const FIELD_LABELS = {
    name: 'Name', ein: 'EIN / Tax ID', contactName: 'Contact person',
    email: 'Email', phone: 'Phone', website: 'Website',
    industry: 'Industry', naics: 'NAICS', legalStructure: 'Legal structure',
    address: 'Address', city: 'City', state: 'State', zip: 'ZIP',
    commodities: 'Commodities', serviceArea: 'Service area', variants: 'Variants / DBAs',
  };

  const isArray = (v) => Array.isArray(v);
  const hasValue = (v) => isArray(v) ? v.length > 0 : v != null && v !== '';

  // Dynamically discover fields: show any NATIVE_EDITABLE_FIELDS where at least one side has a value
  const { scalarFields, arrayFields } = useMemo(() => {
    const scalar = [];
    const arr = [];
    NATIVE_EDITABLE_FIELDS.forEach((key) => {
      const sv = sourceEntity[key];
      const tv = targetEntity[key];
      if (!hasValue(sv) && !hasValue(tv)) return; // skip if both empty
      const label = FIELD_LABELS[key] || key.replace(/([A-Z])/g, ' $1').replace(/^./, (s) => s.toUpperCase());
      if (isArray(sv) || isArray(tv)) {
        arr.push({ key, label });
      } else {
        scalar.push({ key, label });
      }
    });
    return { scalarFields: scalar, arrayFields: arr };
  }, [sourceEntity, targetEntity]);

  // Per-field resolution state — 'same' | 'source' | 'target' | 'custom' (scalar) / 'union' (array)
  const [resolutions, setResolutions] = useState(() => {
    const init = {};
    NATIVE_EDITABLE_FIELDS.forEach((key) => {
      const sv = sourceEntity[key];
      const tv = targetEntity[key];
      if (!hasValue(sv) && !hasValue(tv)) return;
      if (isArray(sv) || isArray(tv)) {
        const sArr = sv || [];
        const tArr = tv || [];
        const same = sArr.length === tArr.length && sArr.every((v, i) => v === tArr[i]);
        init[key] = same ? 'same' : 'union';
      } else {
        init[key] = String(sv || '') === String(tv || '') ? 'same' : 'target';
      }
    });
    return init;
  });

  const [customValues, setCustomValues] = useState({});

  // Editable union lists for array fields
  const [unionLists, setUnionLists] = useState(() => {
    const init = {};
    NATIVE_EDITABLE_FIELDS.forEach((key) => {
      const sv = sourceEntity[key];
      const tv = targetEntity[key];
      if (isArray(sv) || isArray(tv)) {
        init[key] = [...new Set([...(tv || []), ...(sv || [])])];
      }
    });
    return init;
  });

  const setResolution = (key, choice) => setResolutions((prev) => ({ ...prev, [key]: choice }));

  const removeFromUnion = (fieldKey, item) => {
    setUnionLists((prev) => ({ ...prev, [fieldKey]: prev[fieldKey].filter((v) => v !== item) }));
  };

  // Count how many fields differ
  const diffCount = useMemo(() => {
    return [...scalarFields, ...arrayFields].filter(({ key }) => resolutions[key] !== 'same').length;
  }, [scalarFields, arrayFields, resolutions]);

  // Build native overrides from resolution choices
  const buildOverrides = () => {
    const overrides = {};
    scalarFields.forEach(({ key }) => {
      const choice = resolutions[key];
      if (choice === 'same' || choice === 'target') return;
      if (choice === 'source') overrides[key] = sourceEntity[key] || '';
      if (choice === 'custom') overrides[key] = customValues[key] || '';
    });
    arrayFields.forEach(({ key }) => {
      const choice = resolutions[key];
      if (choice === 'same' || choice === 'target') return;
      if (choice === 'source') overrides[key] = sourceEntity[key] || [];
      if (choice === 'union') overrides[key] = unionLists[key];
    });
    return overrides;
  };

  // Compute relationships that will migrate
  const sourceRels = relationships.filter(
    (r) => r.source === sourceEntity.id || r.target === sourceEntity.id
  );

  // Shared neighbors
  const sourceNeighborIds = new Set(sourceRels.map((r) => (r.source === sourceEntity.id ? r.target : r.source)));
  const targetRels = relationships.filter(
    (r) => r.source === targetEntity.id || r.target === targetEntity.id
  );
  const targetNeighborIds = new Set(targetRels.map((r) => (r.source === targetEntity.id ? r.target : r.source)));
  const sharedNeighborIds = [...sourceNeighborIds].filter((id) => targetNeighborIds.has(id));
  const sharedNeighborNames = sharedNeighborIds
    .map((id) => allEntities.find((e) => e.id === id)?.name)
    .filter(Boolean);

  // Similarity warning
  const sameIndustry = sourceEntity.industry === targetEntity.industry;
  const sameState = sourceEntity.state === targetEntity.state;
  const lowSimilarity = !sameIndustry && !sameState;

  return (
    <>
      {/* Header with back button */}
      <div className="px-6 py-3 border-b flex items-center gap-3" style={{ borderColor: QB.cardBorder, backgroundColor: '#FAFAFA' }}>
        <button onClick={onBack} className="p-1 rounded hover:bg-gray-200"><ChevronLeft size={16} style={{ color: QB.textSecondary }} /></button>
        <div className="flex-1">
          <div className="text-[10px] font-semibold tracking-wider" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
            MERGE COMPARISON
          </div>
        </div>
        {diffCount > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: QB.orangeLight, color: QB.orange }}>
            {diffCount} field{diffCount !== 1 ? 's' : ''} differ
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {/* Source → Target visual */}
        <div className="flex items-center gap-3">
          <div className="flex-1 p-3 rounded border text-center" style={{ borderColor: QB.cardBorder }}>
            <div className="w-10 h-10 rounded mx-auto mb-1.5 flex items-center justify-center" style={{ backgroundColor: sourceInd.color + '15' }}>
              <Building2 size={16} style={{ color: sourceInd.color }} />
            </div>
            <div className="text-xs font-medium" style={{ color: QB.textPrimary }}>{sourceEntity.name}</div>
            <div className="text-[10px]" style={{ color: QB.textMuted }}>{sourceEntity.city}, {sourceEntity.state}</div>
            <div className="text-[9px] mt-0.5" style={{ color: QB.textMuted }}>source (retiring)</div>
          </div>
          <div className="flex flex-col items-center gap-0.5 shrink-0">
            <ArrowRight size={18} style={{ color: QB.purple }} />
            <span className="text-[9px] font-medium" style={{ color: QB.purple }}>into</span>
          </div>
          <div className="flex-1 p-3 rounded border-2 text-center" style={{ borderColor: QB.purple + '40', backgroundColor: QB.purpleLight + '15' }}>
            <div className="w-10 h-10 rounded mx-auto mb-1.5 flex items-center justify-center" style={{ backgroundColor: targetInd.color + '15' }}>
              <Building2 size={16} style={{ color: targetInd.color }} />
            </div>
            <div className="text-xs font-medium" style={{ color: QB.textPrimary }}>{targetEntity.name}</div>
            <div className="text-[10px]" style={{ color: QB.textMuted }}>{targetEntity.city}, {targetEntity.state}</div>
            <div className="text-[9px] mt-0.5 font-medium" style={{ color: QB.purple }}>surviving</div>
          </div>
        </div>

        {/* Low similarity warning */}
        {lowSimilarity && (
          <div className="flex items-center gap-2 px-3 py-2 rounded text-[11px]"
            style={{ backgroundColor: QB.orangeLight, color: QB.orange, border: '1px solid ' + QB.orange + '30' }}>
            <AlertTriangle size={13} />
            <span>These entities have low similarity. Different industry and location. Are you sure they're the same?</span>
          </div>
        )}

        {/* ── Per-field resolution: scalar fields ── */}
        <div>
          <div className="text-[10px] font-semibold tracking-wider mb-2" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
            FIELD RESOLUTION
          </div>
          <div className="text-[10px] mb-2" style={{ color: QB.purple }}>
            Choose which value to keep for each differing field. These become native overrides on the surviving entity.
          </div>
          <div className="rounded border overflow-hidden" style={{ borderColor: QB.cardBorder }}>
            {scalarFields.map(({ key, label }, i) => {
              const sv = String(sourceEntity[key] || '');
              const tv = String(targetEntity[key] || '');
              const choice = resolutions[key];
              const isSame = choice === 'same';

              return (
                <div key={key} className={i > 0 ? 'border-t' : ''} style={{ borderColor: '#F0F0F0' }}>
                  <div className="flex items-center justify-between px-3 py-1.5" style={{ backgroundColor: '#FAFAFA' }}>
                    <span className="text-[11px] font-medium" style={{ color: QB.textSecondary }}>{label}</span>
                    {isSame && (
                      <span className="text-[10px] flex items-center gap-1" style={{ color: QB.green }}>
                        <Check size={9} /> same
                      </span>
                    )}
                  </div>
                  {isSame ? (
                    <div className="px-3 pb-2 text-xs" style={{ color: QB.textPrimary }}>{tv || '\u2014'}</div>
                  ) : (
                    <div className="px-3 pb-2.5 space-y-1">
                      <label className="flex items-center gap-2 cursor-pointer text-[11px] py-0.5 px-1.5 rounded hover:bg-gray-50">
                        <input type="radio" name={'res-' + key} checked={choice === 'source'}
                          onChange={() => setResolution(key, 'source')}
                          style={{ accentColor: QB.purple }} />
                        <span style={{ color: choice === 'source' ? QB.textPrimary : QB.textMuted }}>
                          Source: <strong>{sv || '\u2014'}</strong>
                        </span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer text-[11px] py-0.5 px-1.5 rounded hover:bg-gray-50">
                        <input type="radio" name={'res-' + key} checked={choice === 'target'}
                          onChange={() => setResolution(key, 'target')}
                          style={{ accentColor: QB.purple }} />
                        <span style={{ color: choice === 'target' ? QB.textPrimary : QB.textMuted }}>
                          Target: <strong>{tv || '\u2014'}</strong>
                        </span>
                        <span className="text-[9px] px-1 rounded" style={{ backgroundColor: QB.purpleLight, color: QB.purple }}>default</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer text-[11px] py-0.5 px-1.5 rounded hover:bg-gray-50">
                        <input type="radio" name={'res-' + key} checked={choice === 'custom'}
                          onChange={() => setResolution(key, 'custom')}
                          style={{ accentColor: QB.purple }} />
                        <span style={{ color: choice === 'custom' ? QB.textPrimary : QB.textMuted }}>Custom:</span>
                        {choice === 'custom' && (
                          <input
                            value={customValues[key] || ''}
                            onChange={(e) => setCustomValues((p) => ({ ...p, [key]: e.target.value }))}
                            autoFocus
                            className="flex-1 px-2 py-1 rounded border text-[11px] focus:outline-none"
                            style={{ borderColor: QB.purple + '40', color: QB.textPrimary }}
                          />
                        )}
                      </label>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Per-field resolution: array fields ── */}
        {arrayFields.map(({ key, label }) => {
          const sv = sourceEntity[key] || [];
          const tv = targetEntity[key] || [];
          const choice = resolutions[key];
          const isSame = choice === 'same';

          if (sv.length === 0 && tv.length === 0) return null;

          return (
            <div key={key}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-semibold tracking-wider" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
                  {label.toUpperCase()}
                </span>
                {isSame && (
                  <span className="text-[10px] flex items-center gap-1" style={{ color: QB.green }}>
                    <Check size={9} /> same
                  </span>
                )}
              </div>
              {isSame ? (
                <div className="flex flex-wrap gap-1">
                  {tv.map((c, i) => (
                    <span key={i} className="px-1.5 py-0.5 rounded text-[10px]" style={{ backgroundColor: '#F0F1F3', color: QB.textSecondary }}>{c}</span>
                  ))}
                </div>
              ) : (
                <>
                  <div className="flex gap-1.5 mb-2">
                    {[
                      { val: 'source', label: 'Source only' },
                      { val: 'target', label: 'Target only' },
                      { val: 'union', label: 'Union (recommended)' },
                    ].map((opt) => (
                      <button key={opt.val} onClick={() => setResolution(key, opt.val)}
                        className="px-2 py-1 rounded text-[10px] border transition-colors"
                        style={{
                          borderColor: choice === opt.val ? QB.purple + '60' : QB.cardBorder,
                          backgroundColor: choice === opt.val ? QB.purpleLight + '25' : 'white',
                          color: choice === opt.val ? QB.purple : QB.textMuted,
                          fontWeight: choice === opt.val ? 500 : 400,
                        }}>
                        {opt.label}
                      </button>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {(choice === 'source' ? sv : choice === 'target' ? tv : unionLists[key]).map((c, i) => {
                      const inSource = sv.includes(c);
                      const inTarget = tv.includes(c);
                      const isSourceOnly = inSource && !inTarget;
                      const isTargetOnly = !inSource && inTarget;
                      return (
                        <span key={i} className="px-1.5 py-0.5 rounded text-[10px] flex items-center gap-1"
                          style={{
                            backgroundColor: isSourceOnly ? QB.orangeLight : isTargetOnly ? QB.purpleLight + '40' : '#F0F1F3',
                            color: isSourceOnly ? QB.orange : isTargetOnly ? QB.purple : QB.textSecondary,
                            border: isSourceOnly ? '1px solid ' + QB.orange + '30' : isTargetOnly ? '1px solid ' + QB.purple + '30' : 'none',
                          }}>
                          {c}
                          {choice === 'union' && (
                            <button onClick={() => removeFromUnion(key, c)} className="opacity-60 hover:opacity-100">
                              <X size={8} />
                            </button>
                          )}
                        </span>
                      );
                    })}
                  </div>
                  {choice === 'union' && (
                    <div className="flex items-center gap-2 mt-1.5 text-[9px]" style={{ color: QB.textMuted }}>
                      <span style={{ color: QB.orange }}>{'\u25CF'}</span> from source
                      <span style={{ color: QB.purple }}>{'\u25CF'}</span> from target
                      <span>{'\u25CF'}</span> shared
                      <span className="ml-1">{'\u00B7'} click {'\u00D7'} to remove</span>
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}

        {/* Shared neighbors */}
        {sharedNeighborNames.length > 0 && (
          <div className="flex items-center gap-2 px-3 py-2 rounded text-[11px]"
            style={{ backgroundColor: QB.greenLight + '60', color: QB.greenDark }}>
            <Users size={12} />
            <span>Shared neighbors: {sharedNeighborNames.join(', ')}</span>
          </div>
        )}

        {/* What happens */}
        <div>
          <div className="text-[10px] font-semibold tracking-wider mb-2" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
            WHAT HAPPENS ON MERGE
          </div>
          <div className="space-y-1.5 text-xs" style={{ color: QB.textSecondary }}>
            <div className="flex items-start gap-2"><ArrowRight size={10} className="mt-0.5 shrink-0" style={{ color: QB.purple }} /> Your {sourceRels.length} relationship{sourceRels.length !== 1 ? 's' : ''} move to {targetEntity.name}</div>
            <div className="flex items-start gap-2"><ArrowRight size={10} className="mt-0.5 shrink-0" style={{ color: QB.purple }} /> Field resolutions become native overrides on the surviving entity</div>
            <div className="flex items-start gap-2"><ArrowRight size={10} className="mt-0.5 shrink-0" style={{ color: QB.purple }} /> Source entity hidden from YOUR graph</div>
            <div className="flex items-start gap-2"><ArrowRight size={10} className="mt-0.5 shrink-0" style={{ color: QB.textMuted }} /> Source entity unchanged for other users</div>
            <div className="flex items-start gap-2"><ArrowRight size={10} className="mt-0.5 shrink-0" style={{ color: QB.textMuted }} /> System receives this as a merge signal</div>
          </div>
        </div>

        {/* Optional reason */}
        <div>
          <label className="text-[11px] mb-1 block" style={{ color: QB.textSecondary }}>
            Reason (optional)
          </label>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Same company, different name"
            className="w-full px-3 py-2 rounded border text-xs focus:outline-none"
            style={{ borderColor: QB.cardBorder, color: QB.textPrimary }}
          />
        </div>
      </div>

      {/* Footer */}
      <div className="px-6 py-4 border-t flex gap-2 shrink-0" style={{ borderColor: QB.cardBorder }}>
        <button onClick={onBack}
          className="flex-1 py-2.5 rounded text-xs border transition-colors hover:bg-gray-50"
          style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
          Back
        </button>
        <button
          onClick={() => onConfirm(reason, buildOverrides())}
          className="flex-1 py-2.5 rounded text-xs font-medium text-white flex items-center justify-center gap-1.5"
          style={{ backgroundColor: QB.purple }}
        >
          <GitMerge size={12} /> Confirm native merge
        </button>
      </div>
    </>
  );
}

// ── Step 3: Success confirmation ────────────────────────

function MergeSuccess({ sourceEntity, targetEntity, migratedCount, onUndo, onClose }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 py-12">
      <div className="w-14 h-14 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: QB.purpleLight }}>
        <Check size={24} style={{ color: QB.purple }} />
      </div>
      <h3 className="text-base font-medium mb-1" style={{ color: QB.textPrimary }}>Native merge complete</h3>
      <p className="text-xs text-center mb-1" style={{ color: QB.textSecondary }}>
        {sourceEntity.name} merged into {targetEntity.name}
      </p>
      <div className="text-[11px] text-center space-y-0.5 mb-6" style={{ color: QB.textMuted }}>
        <div>{migratedCount} relationship{migratedCount !== 1 ? 's' : ''} migrated</div>
      </div>
      <div className="flex gap-3">
        <button onClick={onUndo}
          className="flex items-center gap-1.5 px-4 py-2 rounded text-xs border transition-colors hover:bg-gray-50"
          style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
          <Undo2 size={11} /> Undo
        </button>
        <button onClick={onClose}
          className="px-4 py-2 rounded text-xs font-medium text-white"
          style={{ backgroundColor: QB.purple }}>
          Done
        </button>
      </div>
    </div>
  );
}

// ── Main modal ──────────────────────────────────────────

/**
 * Full merge flow modal: Search → Compare → Confirm.
 *
 * Props:
 *  - sourceEntity: the entity being merged (will be retired from user's view)
 *  - allEntities: all entities for search
 *  - relationships: all relationships for migration computation
 *  - onConfirmMerge: (sourceEntity, targetEntity, reason) => void
 *  - onUndoMerge: (mergeId) => void
 *  - onClose: close the modal
 */
export function MergeFlowModal({
  sourceEntity,
  allEntities,
  relationships,
  onConfirmMerge,
  onUndoMerge,
  onClose,
}) {
  const [step, setStep] = useState('search'); // 'search' | 'compare' | 'success'
  const [targetEntity, setTargetEntity] = useState(null);
  const [mergeResult, setMergeResult] = useState(null);

  const handleSelect = (entity) => {
    setTargetEntity(entity);
    setStep('compare');
  };

  const handleConfirm = (reason, mergeResolution) => {
    const sourceRels = relationships.filter(
      (r) => r.source === sourceEntity.id || r.target === sourceEntity.id
    );
    const result = onConfirmMerge?.(sourceEntity, targetEntity, reason, mergeResolution);
    setMergeResult({ migratedCount: sourceRels.length, mergeId: result?.id });
    setStep('success');
  };

  const handleUndo = () => {
    if (mergeResult?.mergeId) onUndoMerge?.(mergeResult.mergeId);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-10" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30" />
      <div
        className="relative bg-white rounded-lg shadow-2xl w-full max-w-lg max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-3.5 border-b shrink-0" style={{ borderColor: QB.cardBorder }}>
          <div className="flex items-center gap-2">
            <GitMerge size={16} style={{ color: QB.purple }} />
            <div>
              <h2 className="text-sm font-medium" style={{ color: QB.textPrimary }}>
                {step === 'search' && 'Merge entity'}
                {step === 'compare' && 'Confirm merge'}
                {step === 'success' && 'Merge complete'}
              </h2>
              <p className="text-[10px]" style={{ color: QB.purple }}>Native perspective</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-gray-100">
            <X size={16} style={{ color: QB.textMuted }} />
          </button>
        </div>

        {/* Step content */}
        {step === 'search' && (
          <MergeSearch
            sourceEntity={sourceEntity}
            allEntities={allEntities}
            relationships={relationships}
            onSelect={handleSelect}
            onCancel={onClose}
          />
        )}

        {step === 'compare' && targetEntity && (
          <MergeCompare
            sourceEntity={sourceEntity}
            targetEntity={targetEntity}
            relationships={relationships}
            allEntities={allEntities}
            onConfirm={handleConfirm}
            onBack={() => setStep('search')}
          />
        )}

        {step === 'success' && targetEntity && (
          <MergeSuccess
            sourceEntity={sourceEntity}
            targetEntity={targetEntity}
            migratedCount={mergeResult?.migratedCount || 0}
            onUndo={handleUndo}
            onClose={onClose}
          />
        )}
      </div>
    </div>
  );
}
