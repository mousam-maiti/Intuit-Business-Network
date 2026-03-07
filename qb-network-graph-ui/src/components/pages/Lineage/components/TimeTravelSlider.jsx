import { useMemo } from 'react';
import { QB } from '@/constants/colors';
import { getDecisionColor } from './DecisionBadge';

const DECISION_LABELS = { MERGE: 'Merged', NEW_ENTITY: 'Created', REVIEW: 'Review', NO_MERGE_FOUND: 'No match' };

// Layout constants
const TRACK_Y = 70;          // center line Y position
const BRANCH_LEN = 32;       // length of the 45° diagonal stem
const STATION_R = 5;         // station dot radius
const ACTIVE_R = 7;          // active station dot radius
const TOTAL_H = 140;         // SVG height

/**
 * Metro-line time travel with a single horizontal trunk and
 * stations branching off at 45° angles, alternating above/below.
 */
export function TimeTravelSlider({ entries, selectedDate, onChange, filteredCount }) {
  const stations = useMemo(() => {
    if (!entries.length) return [];
    const sorted = [...entries].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    const n = sorted.length;
    // Even spacing: line width (4%–92%) / number of entries
    const lineStart = 4;
    const lineEnd = 92;
    const step = n > 1 ? (lineEnd - lineStart) / n : 0;
    return sorted.map((e, i) => {
      const d = new Date(e.created_at);
      return {
        id: e.audit_id,
        pct: lineStart + step * i + step / 2, // center each station in its segment
        color: getDecisionColor(e.decision),
        label: DECISION_LABELS[e.decision] || e.decision,
        date: d,
        dateStr: e.created_at,
        above: i % 2 === 0, // odd (1st,3rd,5th) top, even (2nd,4th,6th) bottom
      };
    });
  }, [entries]);

  const activeIndex = useMemo(() => {
    if (!selectedDate || !stations.length) return -1;
    const target = new Date(selectedDate).getTime();
    let best = -1;
    let bestDist = Infinity;
    stations.forEach((s, i) => {
      const dist = Math.abs(s.date.getTime() - target);
      if (dist < bestDist) { bestDist = dist; best = i; }
    });
    return best;
  }, [selectedDate, stations]);

  if (!stations.length) return null;

  const handleStationClick = (station) => {
    if (activeIndex >= 0 && stations[activeIndex]?.id === station.id) {
      onChange(null);
    } else {
      onChange(station.dateStr);
    }
  };

  const handleDateInput = (e) => {
    if (!e.target.value) onChange(null);
    else onChange(new Date(e.target.value + 'T23:59:59.999Z').toISOString());
  };

  const dateInputValue = selectedDate ? new Date(selectedDate).toISOString().slice(0, 10) : '';
  const minISO = stations[0].date.toISOString().slice(0, 10);
  const nowISO = new Date().toISOString().slice(0, 10);
  const nowPct = 96; // "Now" terminus position

  return (
    <div className="px-4 py-3 rounded-lg" style={{ backgroundColor: QB.cardBg, border: '1px solid ' + QB.cardBorder }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2 text-xs font-medium" style={{ color: QB.textPrimary }}>
          <span>Time travel</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ backgroundColor: '#F0F1F3', color: QB.textMuted }}>
            {filteredCount}/{entries.length} events
          </span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={dateInputValue}
            min={minISO}
            max={nowISO}
            onChange={handleDateInput}
            className="text-[11px] px-2 py-1 rounded border focus:outline-none"
            style={{ borderColor: QB.cardBorder, color: QB.textPrimary }}
          />
          {selectedDate && (
            <button
              onClick={() => onChange(null)}
              className="text-[10px] px-2 py-1 rounded"
              style={{ backgroundColor: QB.greenLight, color: QB.greenDark }}
            >
              Now
            </button>
          )}
        </div>
      </div>

      {/* SVG metro diagram */}
      <svg
        viewBox={`0 0 1000 ${TOTAL_H}`}
        className="w-full"
        style={{ height: TOTAL_H }}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Main trunk line (gray) */}
        <line
          x1={stations[0].pct * 10} y1={TRACK_Y}
          x2={nowPct * 10} y2={TRACK_Y}
          stroke={QB.cardBorder} strokeWidth={3} strokeLinecap="round"
        />

        {/* Green progress overlay up to selected station */}
        {activeIndex >= 0 && (
          <line
            x1={stations[0].pct * 10} y1={TRACK_Y}
            x2={stations[activeIndex].pct * 10} y2={TRACK_Y}
            stroke={QB.green} strokeWidth={3} strokeLinecap="round"
          />
        )}

        {/* Stations */}
        {stations.map((s, i) => {
          const cx = s.pct * 10; // trunk junction x
          const isActive = i === activeIndex;
          const isPast = activeIndex < 0 || i <= activeIndex;
          const dir = s.above ? -1 : 1;

          // 45° diagonal: dx = dy = BRANCH_LEN * cos(45°)
          const offset = BRANCH_LEN * 0.707;
          const stationX = cx + offset;
          const stationY = TRACK_Y + dir * offset;

          // Label position — further out from station
          const labelX = stationX + 6;
          const labelY = stationY + dir * 4;

          const r = isActive ? ACTIVE_R : STATION_R;
          const trunkColor = isPast ? s.color : QB.cardBorder;
          const dateText = s.date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

          return (
            <g
              key={s.id}
              className="cursor-pointer"
              onClick={() => handleStationClick(s)}
            >
              {/* 45° diagonal stem */}
              <line
                x1={cx} y1={TRACK_Y}
                x2={stationX} y2={stationY}
                stroke={trunkColor} strokeWidth={2} strokeLinecap="round"
              />

              {/* Junction dot on trunk */}
              <circle cx={cx} cy={TRACK_Y} r={3} fill={trunkColor} />

              {/* Station dot */}
              <circle
                cx={stationX} cy={stationY} r={r}
                fill={isPast ? s.color : QB.cardBorder}
                stroke={QB.cardBg} strokeWidth={2}
              />
              {isActive && (
                <circle
                  cx={stationX} cy={stationY} r={r + 3}
                  fill="none" stroke={s.color} strokeWidth={2} opacity={0.5}
                />
              )}

              {/* Date label */}
              <text
                x={labelX} y={labelY}
                textAnchor="start"
                dominantBaseline={s.above ? 'auto' : 'hanging'}
                fontSize={10}
                fontWeight={isActive ? 600 : 400}
                fill={isActive ? QB.textPrimary : QB.textMuted}
              >
                {dateText}
              </text>

              {/* Decision label */}
              <text
                x={labelX} y={labelY + dir * 12}
                textAnchor="start"
                dominantBaseline={s.above ? 'auto' : 'hanging'}
                fontSize={9}
                fill={s.color}
                fontWeight={500}
              >
                {s.label}
              </text>
            </g>
          );
        })}

        {/* "Now" terminus */}
        <g className="cursor-pointer" onClick={() => onChange(null)}>
          <circle
            cx={nowPct * 10} cy={TRACK_Y}
            r={activeIndex < 0 ? ACTIVE_R : 4}
            fill={activeIndex < 0 ? QB.green : QB.cardBorder}
            stroke={QB.cardBg} strokeWidth={2}
          />
          {activeIndex < 0 && (
            <circle
              cx={nowPct * 10} cy={TRACK_Y} r={ACTIVE_R + 3}
              fill="none" stroke={QB.green} strokeWidth={2} opacity={0.5}
            />
          )}
          <text
            x={nowPct * 10} y={TRACK_Y + 18}
            textAnchor="middle"
            fontSize={11}
            fontWeight={600}
            fill={activeIndex < 0 ? QB.green : QB.textMuted}
          >
            Now
          </text>
        </g>
      </svg>
    </div>
  );
}
