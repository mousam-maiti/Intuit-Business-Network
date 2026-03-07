import { QB } from '@/constants/colors';

export function EvaluationChain({ steps }) {
  if (!steps || steps.length === 0) return null;

  return (
    <div className="space-y-2">
      {steps.map((s, i) => (
        <div key={i} className="flex gap-2.5 text-[11px]">
          {/* Step number */}
          <div
            className="w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-[10px] font-bold"
            style={{ backgroundColor: QB.purpleLight, color: QB.purpleDark }}
          >
            {typeof s.step === 'number' ? s.step : i + 1}
          </div>

          <div className="flex-1 min-w-0">
            {/* Tool + candidate + score row */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono font-medium" style={{ color: QB.purple }}>
                {s.tool_called}
              </span>
              {s.candidate && (
                <span className="px-1.5 py-0.5 rounded text-[10px]" style={{ backgroundColor: '#F0F1F3', color: QB.textSecondary }}>
                  {s.candidate}
                </span>
              )}
              {s.score != null && (
                <span className="font-medium" style={{ color: s.score >= 0.70 ? QB.green : s.score >= 0.50 ? QB.orange : QB.red }}>
                  {Math.round(s.score * 100)}%
                </span>
              )}
              {s.disqualified && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-medium" style={{ backgroundColor: QB.redLight, color: QB.red }}>
                  Disqualified
                </span>
              )}
              <span style={{ color: QB.textMuted }}>{s.duration_ms}ms</span>
            </div>

            {/* Details */}
            {s.details && (
              <div className="mt-0.5" style={{ color: QB.textSecondary }}>
                {typeof s.details === 'string'
                  ? s.details
                  : Object.entries(s.details).map(([k, v]) => `${k}: ${v}`).join(', ')}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
