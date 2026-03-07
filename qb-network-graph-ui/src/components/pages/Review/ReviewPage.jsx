import { useState, useEffect, useCallback } from 'react';
import { Check, XCircle, GitBranch, Search, Loader2, Star, ArrowRight } from 'lucide-react';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { getPendingMatches, getCandidates, resolveMatch } from '@/api/matching';
import { Widget, ScoreBar } from '@/components/shared';

const TRIGGER_LABELS = {
  AI_AGENT_DETERMINISTIC: 'Deterministic',
  AI_AGENT_EMBEDDING: 'Embedding',
  AI_AGENT_LLM: 'LLM Review',
  AI_AGENT: 'AI Review',
};

function ConfidenceBadge({ value }) {
  const pct = Math.round(value * 100);
  const bg = value >= 0.85 ? '#DCFCE7' : value >= 0.60 ? QB.orangeLight : '#FEE2E2';
  const fg = value >= 0.85 ? '#16A34A' : value >= 0.60 ? QB.orange : '#DC2626';
  return (
    <span className="text-xs font-semibold px-2 py-0.5 rounded" style={{ backgroundColor: bg, color: fg }}>
      {pct}%
    </span>
  );
}

export default function ReviewPage() {
  const [matches, setMatches] = useState([]);
  const [selected, setSelected] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [resolved, setResolved] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    getPendingMatches().then(r => setMatches(r.data));
  }, []);

  const selectMatch = useCallback(async (match) => {
    setSelected(match);
    setCandidates([]);
    setLoadingCandidates(true);
    setError(null);
    try {
      const res = await getCandidates(match.id);
      setCandidates(res.candidates || []);
    } catch (e) {
      setError(`Failed to load candidates: ${e.message || 'Unknown error'}`);
    } finally {
      setLoadingCandidates(false);
    }
  }, []);

  const handleMerge = useCallback(async (candidateGoldenId) => {
    if (!selected) return;
    const matchId = selected.id;
    const m = selected;
    const prevMatches = matches;
    const prevResolved = resolved;

    setMatches(p => p.filter(x => x.id !== matchId));
    setResolved(p => [{ ...m, action: 'merged', at: 'Just now' }, ...p]);
    setSelected(null);
    setCandidates([]);
    setError(null);

    try {
      await resolveMatch(matchId, 'accept', candidateGoldenId);
    } catch (e) {
      setMatches(prevMatches);
      setResolved(prevResolved);
      setError(`Merge failed: ${e.message || 'Unknown error'}`);
    }
  }, [selected, matches, resolved]);

  const handleReject = useCallback(async () => {
    if (!selected) return;
    const matchId = selected.id;
    const m = selected;
    const prevMatches = matches;
    const prevResolved = resolved;

    setMatches(p => p.filter(x => x.id !== matchId));
    setResolved(p => [{ ...m, action: 'rejected', at: 'Just now' }, ...p]);
    setSelected(null);
    setCandidates([]);
    setError(null);

    try {
      await resolveMatch(matchId, 'reject');
    } catch (e) {
      setMatches(prevMatches);
      setResolved(prevResolved);
      setError(`Reject failed: ${e.message || 'Unknown error'}`);
    }
  }, [selected, matches, resolved]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 shrink-0">
        <h1 className="text-xl font-normal" style={{ color: QB.textPrimary }}>
          Review Pending Matches
          <span className="text-sm font-normal ml-2" style={{ color: QB.textMuted }}>
            &middot; {matches.length} pending
          </span>
        </h1>
      </div>

      {error && (
        <div className="mx-6 mb-2 px-4 py-2 rounded text-xs font-medium flex items-center justify-between shrink-0" style={{ backgroundColor: '#FEE2E2', color: '#DC2626' }}>
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-4 text-xs underline">Dismiss</button>
        </div>
      )}

      {/* Master-detail layout */}
      <div className="flex-1 flex min-h-0">
        {/* Left panel — Orphan list */}
        <div className="w-80 shrink-0 border-r overflow-y-auto" style={{ borderColor: QB.cardBorder }}>
          {matches.length === 0 ? (
            <div className="text-center py-12">
              <Check size={28} style={{ color: QB.green }} className="mx-auto mb-2" />
              <p className="text-sm" style={{ color: QB.textMuted }}>All matches reviewed!</p>
            </div>
          ) : (
            <div className="py-1">
              {matches.map(m => {
                const isSelected = selected?.id === m.id;
                return (
                  <button
                    key={m.id}
                    onClick={() => selectMatch(m)}
                    className="w-full text-left px-4 py-3 border-b transition-colors"
                    style={{
                      borderColor: QB.cardBorder,
                      backgroundColor: isSelected ? QB.purpleLight : 'transparent',
                    }}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <ConfidenceBadge value={m.confidence} />
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: '#F4F5F7', color: QB.textMuted }}>
                        {TRIGGER_LABELS[m.triggerType] || TRIGGER_LABELS.AI_AGENT}
                      </span>
                    </div>
                    <div className="text-sm font-medium truncate" style={{ color: QB.textPrimary }}>
                      {m.inputName || 'Unknown'}
                    </div>
                    <div className="text-xs truncate" style={{ color: QB.textMuted }}>
                      {m.inputCategory} &middot; {m.inputLocation}
                    </div>
                    <div className="text-[10px] mt-1" style={{ color: QB.textMuted }}>{m.age}</div>
                  </button>
                );
              })}
            </div>
          )}

          {/* Resolved section */}
          {resolved.length > 0 && (
            <div className="px-4 py-3 border-t" style={{ borderColor: QB.cardBorder }}>
              <div className="text-[10px] font-semibold tracking-wider mb-2" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>RESOLVED</div>
              {resolved.map((r, i) => (
                <div key={i} className="flex items-center gap-2 py-1 text-xs" style={{ color: QB.textMuted }}>
                  {r.action === 'merged' ? <Check size={10} style={{ color: QB.green }} /> : <XCircle size={10} style={{ color: '#DC2626' }} />}
                  <span className="truncate" style={{ color: QB.textSecondary }}>
                    {r.action === 'merged' ? 'Merged' : 'Rejected'}: {r.inputName || 'Unknown'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right panel — Detail + Candidates */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {!selected ? (
            <div className="flex flex-col items-center justify-center h-full" style={{ color: QB.textMuted }}>
              <Search size={32} className="mb-3 opacity-40" />
              <p className="text-sm">Select a pending match to review candidates</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Orphan details */}
              <Widget>
                <div className="text-[10px] font-semibold tracking-wider mb-2" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
                  ORPHAN RECORD
                </div>
                <div className="text-lg font-medium mb-1" style={{ color: QB.textPrimary }}>{selected.inputName}</div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs" style={{ color: QB.textSecondary }}>
                  {selected.inputCategory && <span>Category: {selected.inputCategory}</span>}
                  {selected.inputLocation && <span>Location: {selected.inputLocation}</span>}
                  <span>AI Confidence: <ConfidenceBadge value={selected.confidence} /></span>
                  <span className="px-1.5 py-0.5 rounded" style={{ backgroundColor: '#F4F5F7', color: QB.textMuted }}>
                    {TRIGGER_LABELS[selected.triggerType] || TRIGGER_LABELS.AI_AGENT}
                  </span>
                </div>

                {/* Dimension scores */}
                {selected.scores && (
                  <div className="mt-3 grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <ScoreBar label="Name" score={selected.scores.name ?? 0} />
                      <ScoreBar label="Industry" score={selected.scores.industry ?? 0} />
                      <ScoreBar label="Location" score={selected.scores.location ?? 0} />
                      <ScoreBar label="Commodity" score={selected.scores.commodity ?? 0} />
                      <ScoreBar label="Behavioral" score={selected.scores.behavioral ?? 0} />
                    </div>
                    {selected.sharedNeighbors?.length > 0 && (
                      <div>
                        <div className="text-[10px] font-semibold tracking-wider mb-1.5" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
                          SHARED NEIGHBORS ({selected.sharedNeighbors.length})
                        </div>
                        {selected.sharedNeighbors.map((n, i) => (
                          <div key={i} className="text-xs flex items-center gap-1.5 py-0.5" style={{ color: QB.textSecondary }}>
                            <GitBranch size={10} style={{ color: '#ccc' }} /> {n}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </Widget>

              {/* Candidates section */}
              <div>
                <div className="text-[10px] font-semibold tracking-wider mb-2" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
                  CANDIDATE GOLDEN RECORDS
                </div>

                {loadingCandidates ? (
                  <Widget>
                    <div className="flex items-center justify-center py-8 gap-2" style={{ color: QB.textMuted }}>
                      <Loader2 size={16} className="animate-spin" />
                      <span className="text-sm">Searching for candidates...</span>
                    </div>
                  </Widget>
                ) : candidates.length === 0 ? (
                  <Widget>
                    <div className="text-center py-6">
                      <p className="text-sm" style={{ color: QB.textMuted }}>No candidate golden records found</p>
                    </div>
                  </Widget>
                ) : (
                  <div className="space-y-2">
                    {candidates.map(c => {
                      const isAISuggested = c.golden_record_id === selected.candidate?.id;
                      const persona = c.persona || {};
                      const location = persona.location || {};
                      const industry = persona.industry || {};
                      const displayLocation = [location.city_norm, location.state].filter(Boolean).join(', ');
                      const displayIndustry = industry.original_category || (industry.naics_code ? `NAICS ${industry.naics_code}` : '');
                      const score = c.score ?? c.confidence;

                      return (
                        <Widget key={c.golden_record_id}>
                          <div className="flex items-start justify-between">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-sm font-medium truncate" style={{ color: QB.textPrimary }}>
                                  {c.canonical_name || c.golden_record_id}
                                </span>
                                {isAISuggested && (
                                  <span className="shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded flex items-center gap-1" style={{ backgroundColor: QB.purpleLight, color: QB.purpleDark }}>
                                    <Star size={10} /> AI Recommended
                                  </span>
                                )}
                              </div>

                              <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs mb-2" style={{ color: QB.textMuted }}>
                                <span>{c.golden_record_id}</span>
                                {displayIndustry && <span>{displayIndustry}</span>}
                                {displayLocation && <span>{displayLocation}</span>}
                                <span>{c.source_count} source{c.source_count !== 1 ? 's' : ''}</span>
                              </div>

                              {/* Score bar */}
                              <div className="flex items-center gap-2 text-xs">
                                <span className="w-20 shrink-0" style={{ color: QB.textMuted }}>Similarity</span>
                                <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: '#E5E7EB' }}>
                                  <div
                                    className="h-full rounded-full transition-all"
                                    style={{
                                      width: `${Math.round(score * 100)}%`,
                                      backgroundColor: score >= 0.85 ? QB.green : score >= 0.60 ? QB.orange : QB.red,
                                    }}
                                  />
                                </div>
                                <span className="w-8 text-right font-medium" style={{ color: QB.textPrimary }}>
                                  {Math.round(score * 100)}%
                                </span>
                              </div>

                              {/* Name variants */}
                              {c.name_variants?.length > 0 && (
                                <div className="mt-1.5 text-[10px]" style={{ color: QB.textMuted }}>
                                  Variants: {c.name_variants.slice(0, 3).join(', ')}
                                  {c.name_variants.length > 3 && ` +${c.name_variants.length - 3} more`}
                                </div>
                              )}
                            </div>

                            {/* Merge button */}
                            <button
                              onClick={() => handleMerge(c.golden_record_id)}
                              className="shrink-0 ml-4 px-3 py-2 rounded text-xs font-medium text-white flex items-center gap-1"
                              style={{ backgroundColor: QB.green }}
                            >
                              <ArrowRight size={12} /> Merge into this
                            </button>
                          </div>
                        </Widget>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Reject button */}
              <button
                onClick={handleReject}
                className="w-full py-2.5 rounded text-xs font-medium border flex items-center justify-center gap-1.5"
                style={{ borderColor: '#FCA5A5', color: '#DC2626', backgroundColor: '#FEF2F2' }}
              >
                <XCircle size={14} /> Reject &mdash; Create New Entity
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
