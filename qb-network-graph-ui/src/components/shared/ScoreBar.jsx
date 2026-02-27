import { QB } from '@/constants/colors';

export function ScoreBar({ label, score }) {
  const color = score >= 0.85 ? QB.green : score >= 0.60 ? QB.orange : QB.red;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 shrink-0" style={{ color: QB.textMuted }}>{label}</span>
      <div className="score-bar-track flex-1">
        <div className="score-bar-fill" style={{ width: (score * 100) + '%', backgroundColor: color }} />
      </div>
      <span className="w-8 text-right font-medium" style={{ color: QB.textPrimary }}>
        {Math.round(score * 100)}%
      </span>
    </div>
  );
}
