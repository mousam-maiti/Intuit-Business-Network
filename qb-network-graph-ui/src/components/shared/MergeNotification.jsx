import { Link2, X } from 'lucide-react';
import { QB } from '@/constants/colors';

export function MergeNotification({ onDismiss }) {
  return (
    <div
      className="mx-6 mt-3 mb-1 flex items-center gap-3 px-4 py-2.5 rounded border text-xs"
      style={{ backgroundColor: QB.purpleLight, borderColor: QB.purple + '40', color: QB.purpleDark }}
    >
      <Link2 size={14} />
      <span className="flex-1">
        <strong>Entity merged:</strong> &ldquo;Bob&rsquo;s Plumbing&rdquo; and &ldquo;BP LLC&rdquo; were confirmed as the same business. 3 relationships migrated.
      </span>
      <button onClick={onDismiss} className="p-0.5 rounded hover:bg-white/50"><X size={12} /></button>
    </div>
  );
}
