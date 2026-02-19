import { useEffect, useRef } from 'react';
import { Search, Check, Bot, Sparkles, GitBranch, Building2 } from 'lucide-react';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { fmt } from '@/utils/format';
import { getRelType } from '@/utils/graph';
import { RelTypeBadge } from './RelTypeBadge';
import { ENTITIES, RELATIONSHIPS, AI_TOOLS } from '@/api/mock/data';
import { Globe } from 'lucide-react';

const SUGGESTIONS = [
  'Which vendors also serve my competitors?',
  'Find plumbing suppliers within 2 hops',
  'What is my most critical vendor dependency?',
  'Show me businesses similar to Tool Depot',
];

export function AIChatMessages({ msgs, typing, tools, onSetInput }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: 'smooth' });
  }, [msgs, tools]);

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-4" style={{ backgroundColor: '#F9FAFB' }}>
      {msgs.length === 0 && !typing && (
        <div className="text-center py-10 space-y-4">
          <div className="w-14 h-14 mx-auto rounded-full flex items-center justify-center" style={{ backgroundColor: QB.greenLight }}>
            <Sparkles size={24} style={{ color: QB.green }} />
          </div>
          <div>
            <h2 className="text-base font-medium" style={{ color: QB.textPrimary }}>Intuit Assist</h2>
            <p className="text-sm mt-1" style={{ color: QB.textMuted }}>
              Ask questions about your business network using natural language.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 max-w-lg mx-auto">
            {SUGGESTIONS.map((q, i) => (
              <button key={i} onClick={() => onSetInput(q)} className="text-left text-xs px-3 py-2.5 rounded border bg-white hover:border-gray-300 transition-colors" style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
                {q}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-4 justify-center pt-4">
            {[
              { icon: <Globe size={12} />, label: 'Knowledge graph' },
              { icon: <Search size={12} />, label: 'Vector search' },
              { icon: <GitBranch size={12} />, label: 'Network traverse' },
            ].map((t, i) => (
              <span key={i} className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-full" style={{ backgroundColor: '#F0F1F3', color: QB.textMuted }}>
                {t.icon} {t.label}
              </span>
            ))}
          </div>
        </div>
      )}

      {msgs.map((m, i) => (
        <div key={i}>
          {m.role === 'user' && (
            <div className="flex justify-end">
              <div className="max-w-[70%] px-4 py-2.5 rounded-lg text-sm text-white" style={{ backgroundColor: QB.green }}>{m.content}</div>
            </div>
          )}
          {m.role === 'ai' && (
            <div className="flex gap-3">
              <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-1" style={{ backgroundColor: QB.greenLight }}>
                <Bot size={13} style={{ color: QB.green }} />
              </div>
              <div className="max-w-[80%] space-y-2">
                <div className="px-4 py-3 rounded-lg bg-white border text-sm leading-relaxed" style={{ borderColor: QB.cardBorder, color: QB.textPrimary }}>{m.content}</div>
                {m.entities && (
                  <div className="space-y-1.5">
                    {m.entities.map((eid) => {
                      const e = ENTITIES.find((x) => x.id === eid);
                      if (!e) return null;
                      const ind = getIndustry(e.industry);
                      const dr = RELATIONSHIPS.find((r) => (r.source === 'e1' && r.target === e.id) || (r.target === 'e1' && r.source === e.id));
                      return (
                        <div key={eid} className="flex items-center gap-3 p-3 rounded-lg bg-white border text-xs cursor-pointer hover:shadow-sm transition-shadow" style={{ borderColor: QB.cardBorder }}>
                          <div className="w-8 h-8 rounded flex items-center justify-center" style={{ backgroundColor: ind.color + '12' }}>
                            <Building2 size={14} style={{ color: ind.color }} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium" style={{ color: QB.link }}>{e.name}</div>
                            <div className="text-[11px]" style={{ color: QB.textMuted }}>{ind.label} &middot; {e.city}, {e.state} &middot; {fmt(e.volume)}/yr</div>
                          </div>
                          {dr && <RelTypeBadge type={getRelType(dr, 'e1')} />}
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded" style={{ backgroundColor: e.confidence >= 0.9 ? QB.greenLight : QB.orangeLight, color: e.confidence >= 0.9 ? QB.greenDark : QB.orange }}>
                            {Math.round(e.confidence * 100)}%
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
                {m.followup && (
                  <div className="px-4 py-3 rounded-lg bg-white border text-sm leading-relaxed" style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>{m.followup}</div>
                )}
              </div>
            </div>
          )}
        </div>
      ))}

      {typing && (
        <div className="flex gap-3">
          <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-1" style={{ backgroundColor: QB.greenLight }}>
            <Bot size={13} style={{ color: QB.green }} />
          </div>
          <div className="px-4 py-3 rounded-lg bg-white border space-y-1.5" style={{ borderColor: QB.cardBorder }}>
            {tools.map((t, i) => (
              <div key={i} className="flex items-center gap-2 text-xs" style={{ color: QB.textSecondary }}>
                <Check size={10} style={{ color: QB.green }} />
                <span className="font-mono text-[10px]" style={{ color: QB.textMuted }}>{t.name}</span>
                {t.label}
              </div>
            ))}
            {tools.length === AI_TOOLS.length && (
              <div className="flex gap-1 py-1">
                {[0, 150, 300].map((d) => (
                  <span key={d} className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ backgroundColor: QB.textMuted, animationDelay: d + 'ms' }} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      <div ref={ref} />
    </div>
  );
}
