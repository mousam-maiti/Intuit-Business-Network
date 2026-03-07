import { Building2 } from 'lucide-react';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { Widget } from '@/components/shared';

export function EntitySnapshot({ entity, dateLabel }) {
  if (!entity) return null;

  const ind = getIndustry(entity.industry);

  const Field = ({ label, value }) => {
    if (!value) return null;
    const display = Array.isArray(value) ? value.join(', ') : String(value);
    return (
      <div className="text-xs">
        <span style={{ color: QB.textMuted }}>{label}: </span>
        <span style={{ color: QB.textPrimary }}>{display}</span>
      </div>
    );
  };

  return (
    <Widget title={'STATE AS OF ' + dateLabel}>
      {/* Header */}
      <div className="flex items-center gap-2 mb-3 pb-2 border-b" style={{ borderColor: QB.cardBorder }}>
        <div className="w-8 h-8 rounded flex items-center justify-center" style={{ backgroundColor: ind.color + '15' }}>
          <Building2 size={14} style={{ color: ind.color }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium truncate" style={{ color: QB.textPrimary }}>{entity.name}</div>
          <div className="text-[10px]" style={{ color: QB.textMuted }}>{ind.label}</div>
        </div>
      </div>

      <div className="space-y-1.5">
        <Field label="EIN" value={entity.ein} />
        <Field label="Contact" value={entity.contactName} />
        <Field label="Email" value={entity.email} />
        <Field label="Phone" value={entity.phone} />
        <Field label="Website" value={entity.website} />
        <Field label="Address" value={[entity.address, entity.city, entity.state, entity.zip].filter(Boolean).join(', ')} />
        <Field label="NAICS" value={entity.naics} />
        <Field label="Legal" value={entity.legalStructure} />
        <Field label="Service area" value={entity.serviceArea} />

        {entity.confidence != null && (
          <div className="text-xs">
            <span style={{ color: QB.textMuted }}>Confidence: </span>
            <span className="font-medium" style={{ color: entity.confidence >= 0.85 ? QB.green : entity.confidence >= 0.60 ? QB.orange : QB.red }}>
              {Math.round(entity.confidence * 100)}%
            </span>
          </div>
        )}

        <Field label="Variants" value={entity.variants} />
        <Field label="Commodities" value={entity.commodities} />
      </div>
    </Widget>
  );
}
