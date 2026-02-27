import { QB } from '@/constants/colors';

const LABEL_MAP = {
  name: 'Name', ein: 'EIN', contactName: 'Contact', email: 'Email',
  phone: 'Phone', website: 'Website', industry: 'Industry', naics: 'NAICS',
  legalStructure: 'Legal structure', address: 'Address', city: 'City',
  state: 'State', zip: 'ZIP', confidence: 'Confidence',
  variants: 'Variants', commodities: 'Commodities', serviceArea: 'Service area',
};

function formatValue(val) {
  if (val == null) return '\u2014';
  if (Array.isArray(val)) return val.join(', ');
  if (typeof val === 'number') return val <= 1 ? Math.round(val * 100) + '%' : String(val);
  return String(val);
}

export function FieldDiff({ before, after }) {
  if (!before && !after) return null;

  const allKeys = new Set([
    ...Object.keys(before || {}),
    ...Object.keys(after || {}),
  ]);

  // Only show fields that changed
  const changes = [];
  for (const key of allKeys) {
    if (key === 'id' || key === 'x' || key === 'y') continue;
    const bv = formatValue(before?.[key]);
    const av = formatValue(after?.[key]);
    if (bv !== av) {
      changes.push({ key, label: LABEL_MAP[key] || key, before: bv, after: av });
    }
  }

  if (changes.length === 0) {
    return <div className="text-[11px] italic" style={{ color: QB.textMuted }}>No field changes</div>;
  }

  return (
    <div className="space-y-1.5">
      {changes.map((c) => (
        <div key={c.key} className="grid grid-cols-[100px_1fr_1fr] gap-2 text-[11px]">
          <span className="truncate" style={{ color: QB.textMuted }}>{c.label}</span>
          <span
            className="px-1.5 py-0.5 rounded truncate"
            style={{ backgroundColor: QB.redLight, color: QB.red, textDecoration: 'line-through' }}
          >
            {c.before}
          </span>
          <span
            className="px-1.5 py-0.5 rounded truncate"
            style={{ backgroundColor: QB.greenLight, color: QB.greenDark }}
          >
            {c.after}
          </span>
        </div>
      ))}
    </div>
  );
}
