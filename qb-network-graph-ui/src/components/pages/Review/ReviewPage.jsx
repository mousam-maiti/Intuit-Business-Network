import { useState } from 'react';
import { Check, XCircle, RotateCcw, GitBranch } from 'lucide-react';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { PENDING_MATCHES } from '@/api/mock/data';
import { Widget, ScoreBar } from '@/components/shared';

export default function ReviewPage() {
  const [matches, setMatches] = useState(PENDING_MATCHES);
  const [resolved, setResolved] = useState([]);
  const act = (id, action) => {
    const m = matches.find((x) => x.id === id);
    setMatches((p) => p.filter((x) => x.id !== id));
    setResolved((p) => [{ ...m, action, at: 'Just now' }, ...p]);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-6 py-4">
        <h1 className="text-xl font-normal" style={{ color: QB.textPrimary }}>
          Match review <span className="text-sm font-normal" style={{ color: QB.textMuted }}>&middot; {matches.length} pending</span>
        </h1>
      </div>
      <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-3">
        {matches.length === 0 && (
          <Widget>
            <div className="text-center py-8">
              <Check size={28} style={{ color: QB.green }} className="mx-auto mb-2" />
              <p className="text-sm" style={{ color: QB.textMuted }}>All matches reviewed!</p>
            </div>
          </Widget>
        )}
        {matches.map((m) => (
          <Widget key={m.id}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold px-2 py-0.5 rounded" style={{ backgroundColor: m.confidence >= 0.75 ? QB.orangeLight : '#FEE2E2', color: m.confidence >= 0.75 ? QB.orange : '#DC2626' }}>
                  {Math.round(m.confidence * 100)}% match
                </span>
                <span className="text-xs" style={{ color: QB.textMuted }}>{m.age}</span>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded" style={{ backgroundColor: '#F4F5F7', color: QB.textMuted }}>Tier 2 &mdash; AI Persona Match</span>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="p-3 rounded" style={{ backgroundColor: '#F4F5F7' }}>
                <div className="text-[10px] font-semibold tracking-wider mb-1" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>INPUT</div>
                <div className="text-sm font-medium" style={{ color: QB.textPrimary }}>{m.inputName}</div>
                <div className="text-xs" style={{ color: QB.textMuted }}>{m.inputCategory} &middot; {m.inputLocation}</div>
              </div>
              <div className="p-3 rounded" style={{ backgroundColor: QB.purpleLight }}>
                <div className="text-[10px] font-semibold tracking-wider mb-1" style={{ color: QB.purpleDark, letterSpacing: '0.08em' }}>CANDIDATE</div>
                <div className="text-sm font-medium" style={{ color: QB.textPrimary }}>{m.candidate.name}</div>
                <div className="text-xs" style={{ color: QB.textMuted }}>{getIndustry(m.candidate.industry).label} &middot; {m.candidate.city}, {m.candidate.state}</div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4 mb-3">
              <div className="space-y-1.5">
                <ScoreBar label="Name" score={m.scores.name} />
                <ScoreBar label="Industry" score={m.scores.industry} />
                <ScoreBar label="Location" score={m.scores.location} />
                <ScoreBar label="Commodity" score={m.scores.commodity} />
              </div>
              <div>
                <div className="text-[10px] font-semibold tracking-wider mb-1.5" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>SHARED NEIGHBORS ({m.sharedNeighbors.length})</div>
                {m.sharedNeighbors.map((n, i) => (
                  <div key={i} className="text-xs flex items-center gap-1.5 py-0.5" style={{ color: QB.textSecondary }}>
                    <GitBranch size={10} style={{ color: '#ccc' }} /> {n}
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-2 pt-3 border-t" style={{ borderColor: QB.cardBorder }}>
              <button onClick={() => act(m.id, 'merged')} className="flex-1 py-2 rounded text-xs font-medium text-white flex items-center justify-center gap-1" style={{ backgroundColor: QB.green }}><Check size={12} /> Merge</button>
              <button onClick={() => act(m.id, 'rejected')} className="flex-1 py-2 rounded text-xs font-medium border flex items-center justify-center gap-1" style={{ borderColor: '#FCA5A5', color: '#DC2626', backgroundColor: '#FEF2F2' }}><XCircle size={12} /> Reject</button>
              <button className="py-2 px-3 rounded text-xs border" style={{ borderColor: QB.cardBorder, color: QB.textMuted }}><RotateCcw size={12} /></button>
            </div>
          </Widget>
        ))}
        {resolved.length > 0 && (
          <div className="pt-3 border-t" style={{ borderColor: QB.cardBorder }}>
            <div className="text-[10px] font-semibold tracking-wider mb-2" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>RESOLVED</div>
            {resolved.map((r, i) => (
              <div key={i} className="flex items-center gap-2 py-1.5 text-xs" style={{ color: QB.textMuted }}>
                {r.action === 'merged' ? <Check size={12} style={{ color: QB.green }} /> : <XCircle size={12} style={{ color: '#DC2626' }} />}
                <span style={{ color: QB.textSecondary }}>{r.action === 'merged' ? 'Merged' : 'Rejected'}: {r.inputName} &#x2194; {r.candidate.name}</span>
                <span className="ml-auto">{r.at}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
