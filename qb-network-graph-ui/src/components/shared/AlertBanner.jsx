import { Check, Link2, AlertTriangle, Plus, X } from 'lucide-react';
import { QB } from '@/constants/colors';

const ALERT_STYLES = {
  connection_added: {
    bg: QB.greenLight,
    border: QB.green + '40',
    color: QB.greenDark,
    Icon: Plus,
  },
  entity_created: {
    bg: QB.greenLight,
    border: QB.green + '40',
    color: QB.greenDark,
    Icon: Check,
  },
  entity_merged: {
    bg: QB.purpleLight,
    border: QB.purple + '40',
    color: QB.purpleDark,
    Icon: Link2,
  },
  merge_review: {
    bg: QB.orangeLight,
    border: QB.orange + '40',
    color: '#92400E',
    Icon: AlertTriangle,
  },
};

export function AlertBanner({ alert, onDismiss, onAction }) {
  const style = ALERT_STYLES[alert.type] || ALERT_STYLES.connection_added;
  const { Icon } = style;

  return (
    <div
      className="mx-6 mt-2 flex items-center gap-3 px-4 py-2.5 rounded border text-xs"
      style={{ backgroundColor: style.bg, borderColor: style.border, color: style.color }}
    >
      <Icon size={14} />
      <span className="flex-1">
        <strong>{alert.title}:</strong> {alert.message}
        {alert.confidence != null && alert.type !== 'connection_added' && (
          <span className="ml-1 opacity-70">({Math.round(alert.confidence * 100)}%)</span>
        )}
      </span>
      {alert.type === 'merge_review' && (
        <button
          onClick={() => onAction(alert)}
          className="px-2.5 py-1 rounded text-[10px] font-medium text-white shrink-0"
          style={{ backgroundColor: QB.orange }}
        >
          Review
        </button>
      )}
      <button onClick={() => onDismiss(alert.id)} className="p-0.5 rounded hover:bg-white/50 shrink-0">
        <X size={12} />
      </button>
    </div>
  );
}
