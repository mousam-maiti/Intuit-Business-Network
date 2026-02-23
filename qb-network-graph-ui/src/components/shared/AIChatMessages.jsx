import { useEffect, useRef } from 'react';
import { Search, Check, Bot, Sparkles, GitBranch, Building2, Globe, ThumbsUp, ThumbsDown, Minus } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, PieChart, Pie, AreaChart, Area, XAxis, YAxis, Tooltip, Cell } from 'recharts';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { fmt } from '@/utils/format';
import { getRelType } from '@/utils/graph';
import { RelTypeBadge } from './RelTypeBadge';
import { ScoreBar } from './ScoreBar';
import { ENTITIES, RELATIONSHIPS } from '@/api/mock/data';

// ── Block Renderers ──────────────────────────────────────

const CHART_COLORS = [QB.green, QB.purple, QB.orange, QB.cyan, QB.red];

function ChartBlock({ chart }) {
  if (!chart) return null;
  const { type, title, data, config = {} } = chart;
  const { dataKey = 'value', xKey = 'name', innerRadius = 35, outerRadius = 55, stroke = QB.green, fill = QB.greenLight } = config;

  return (
    <div className="rounded-lg bg-white border p-3" style={{ borderColor: QB.cardBorder }}>
      {title && <div className="text-[10px] font-semibold tracking-wide mb-2" style={{ color: QB.textMuted }}>{title}</div>}
      <div className="h-36">
        <ResponsiveContainer width="100%" height="100%">
          {type === 'bar' ? (
            <BarChart data={data}>
              <XAxis dataKey={xKey} tick={{ fontSize: 9, fill: QB.textMuted }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 9, fill: QB.textMuted }} axisLine={false} tickLine={false} width={30} />
              <Tooltip contentStyle={{ fontSize: 11 }} />
              <Bar dataKey={dataKey} radius={[2, 2, 0, 0]}>
                {data.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
              </Bar>
            </BarChart>
          ) : type === 'pie' ? (
            <PieChart>
              <Pie data={data} dataKey={dataKey} cx="50%" cy="50%" innerRadius={innerRadius} outerRadius={outerRadius} paddingAngle={2}>
                {data.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ fontSize: 11 }} />
            </PieChart>
          ) : (
            <AreaChart data={data}>
              <XAxis dataKey={xKey} tick={{ fontSize: 9, fill: QB.textMuted }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 9, fill: QB.textMuted }} axisLine={false} tickLine={false} width={30} />
              <Tooltip contentStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey={dataKey} stroke={stroke} fill={fill} strokeWidth={2} />
            </AreaChart>
          )}
        </ResponsiveContainer>
      </div>
      {(type === 'bar' || type === 'pie') && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
          {data.map((d, i) => (
            <span key={i} className="flex items-center gap-1 text-[10px]" style={{ color: QB.textSecondary }}>
              <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: CHART_COLORS[i % CHART_COLORS.length] }} />
              {d[xKey]}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function TableBlock({ table }) {
  if (!table) return null;
  return (
    <div className="rounded-lg bg-white border overflow-hidden" style={{ borderColor: QB.cardBorder }}>
      <table className="w-full text-xs">
        <thead>
          <tr style={{ backgroundColor: '#F9FAFB' }}>
            {table.headers.map((h, i) => (
              <th key={i} className="text-left px-3 py-2 font-semibold" style={{ color: QB.textPrimary }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, ri) => (
            <tr key={ri} className="border-t" style={{ borderColor: QB.cardBorder }}>
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-2" style={{ color: ci === 0 ? QB.textPrimary : QB.textSecondary }}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScoresBlock({ scores }) {
  if (!scores || scores.length === 0) return null;
  return (
    <div className="rounded-lg bg-white border p-3 space-y-2" style={{ borderColor: QB.cardBorder }}>
      {scores.map((s, i) => (
        <ScoreBar key={i} label={s.label} score={s.value} />
      ))}
    </div>
  );
}

function SignalsBlock({ signals }) {
  if (!signals || signals.length === 0) return null;
  const iconMap = {
    positive: <ThumbsUp size={12} style={{ color: QB.green }} />,
    negative: <ThumbsDown size={12} style={{ color: QB.red || '#EF4444' }} />,
    neutral: <Minus size={12} style={{ color: QB.textMuted }} />,
  };
  return (
    <div className="rounded-lg bg-white border p-3 space-y-1.5" style={{ borderColor: QB.cardBorder }}>
      {signals.map((s, i) => (
        <div key={i} className="flex items-center gap-2 text-xs" style={{ color: QB.textSecondary }}>
          {iconMap[s.icon] || iconMap.neutral}
          <span>{s.text}</span>
        </div>
      ))}
    </div>
  );
}

function ActionsBlock({ actions, onAction }) {
  if (!actions || actions.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {actions.map((a, i) => (
        <button
          key={i}
          onClick={() => onAction?.(a.action, a.payload)}
          className="text-xs px-3 py-1.5 rounded-full border font-medium transition-colors hover:shadow-sm"
          style={{ borderColor: QB.green, color: QB.greenDark, backgroundColor: QB.greenLight }}
        >
          {a.label}
        </button>
      ))}
    </div>
  );
}

export function AIChatMessages({ msgs, typing, tools, onSetInput, suggestions, context, onAction }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: 'smooth' });
  }, [msgs, tools]);

  const displaySuggestions = suggestions || [
    'Which vendors also serve my competitors?',
    'Find plumbing suppliers within 2 hops',
    'What is my most critical vendor dependency?',
    'Show me the network summary',
  ];

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-4" style={{ backgroundColor: '#F9FAFB' }}>
      {/* Context indicator bar */}
      {context && msgs.length === 0 && !typing && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs" style={{ backgroundColor: QB.greenLight, color: QB.greenDark }}>
          <Building2 size={12} />
          <span>Context: <strong>{context.entityName}</strong> &middot; {context.page} page</span>
        </div>
      )}

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
            {displaySuggestions.map((q, i) => (
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
                {m.entities && m.entities.length > 0 && (
                  <div className="space-y-1.5">
                    {m.entities.map((eid) => {
                      const e = ENTITIES.find((x) => x.id === eid);
                      if (e) {
                        // Known mock entity — render rich card
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
                      }
                      // Real golden record ID — render compact badge
                      return (
                        <div key={eid} className="inline-flex items-center gap-2 px-3 py-1.5 mr-1.5 mb-1 rounded-lg bg-white border text-xs cursor-pointer hover:shadow-sm transition-shadow" style={{ borderColor: QB.cardBorder }}>
                          <Building2 size={12} style={{ color: QB.green }} />
                          <span className="font-mono text-[11px]" style={{ color: QB.link }}>{eid}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
                {m.table && <TableBlock table={m.table} />}
                {m.chart && <ChartBlock chart={m.chart} />}
                {m.scores && <ScoresBlock scores={m.scores} />}
                {m.signals && <SignalsBlock signals={m.signals} />}
                {m.actions && <ActionsBlock actions={m.actions} onAction={onAction} />}
                {m.followup && (
                  <div className="px-4 py-3 rounded-lg bg-white border text-sm leading-relaxed whitespace-pre-line" style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>{m.followup}</div>
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
            {typing && (
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
