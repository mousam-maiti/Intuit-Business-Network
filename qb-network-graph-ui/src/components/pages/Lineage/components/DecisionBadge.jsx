import { QB } from '@/constants/colors';

const DECISION_STYLES = {
  MERGE:          { bg: QB.greenLight,  color: QB.greenDark, label: 'Merged' },
  NEW_ENTITY:     { bg: QB.purpleLight, color: QB.purpleDark, label: 'Created' },
  REVIEW:         { bg: QB.orangeLight, color: QB.orange, label: 'Review' },
  NO_MERGE_FOUND: { bg: '#F0F1F3',     color: QB.textMuted, label: 'No match' },
  RESTORE:        { bg: QB.purpleLight, color: QB.purple, label: 'Restored' },
};

export function DecisionBadge({ decision }) {
  const s = DECISION_STYLES[decision] || DECISION_STYLES.NO_MERGE_FOUND;
  return (
    <span
      className="inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ backgroundColor: s.bg, color: s.color }}
    >
      {s.label}
    </span>
  );
}

/** Color for the timeline dot matching the decision type. */
export function getDecisionColor(decision) {
  return (DECISION_STYLES[decision] || DECISION_STYLES.NO_MERGE_FOUND).color;
}
