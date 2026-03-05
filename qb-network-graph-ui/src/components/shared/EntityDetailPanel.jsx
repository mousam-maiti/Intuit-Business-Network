import { useState, useEffect } from 'react';
import { Building2, Sparkles, Pencil, GitMerge, Tag, StickyNote, RotateCcw, X, Plus, Check, Network, Share2 } from 'lucide-react';
import { QB } from '@/constants/colors';
import { getIndustry } from '@/constants/industries';
import { fmt } from '@/utils/format';
import { PERSPECTIVE, NATIVE_EDITABLE_FIELDS } from '@/constants/perspective';
import { resolveEntity, isNativeOverride, getGlobalValue } from '@/utils/perspective';
import { Widget } from './Widget';

// ── Shared sub-components ───────────────────────────────

/** Small ⓝ badge indicating a NATIVE override. */
function NativeBadge() {
  return (
    <span
      className="inline-flex items-center justify-center text-[8px] font-bold rounded-full shrink-0"
      style={{ width: 14, height: 14, backgroundColor: QB.purple + '15', color: QB.purple, lineHeight: 1 }}
      title="Your override (Native perspective)"
    >
      n
    </span>
  );
}

/** Shows the GLOBAL value below a NATIVE-overridden field. */
function GlobalFallback({ value }) {
  if (!value) return null;
  return (
    <div className="text-[10px] mt-0.5" style={{ color: QB.textMuted }}>
      Network: {value}
    </div>
  );
}

// ── Edit mode ───────────────────────────────────────────

function EditField({ label, field, value, globalValue, onChange, onReset }) {
  const hasOverride = value !== undefined && value !== null && value !== globalValue;
  return (
    <div>
      <label className="text-[11px] mb-1 block" style={{ color: QB.textSecondary }}>{label}</label>
      <input
        value={value ?? ''}
        onChange={(e) => onChange(field, e.target.value)}
        className="w-full px-2.5 py-2 rounded border text-xs focus:outline-none"
        style={{ borderColor: hasOverride ? QB.purple + '50' : QB.cardBorder, color: QB.textPrimary }}
      />
      <div className="flex items-center justify-between mt-0.5">
        <div className="text-[10px]" style={{ color: QB.textMuted }}>
          Network: {globalValue || '\u2014'}
        </div>
        {hasOverride && (
          <button onClick={() => onReset(field)} className="text-[10px] flex items-center gap-0.5" style={{ color: QB.link }}>
            <RotateCcw size={8} /> Reset
          </button>
        )}
      </div>
    </div>
  );
}

function EditCommodities({ value, globalValue, onChange, onReset }) {
  const [adding, setAdding] = useState('');
  const hasOverride = JSON.stringify(value) !== JSON.stringify(globalValue);

  const addCommodity = () => {
    const trimmed = adding.trim();
    if (trimmed && !value.includes(trimmed)) {
      onChange('commodities', [...value, trimmed]);
      setAdding('');
    }
  };

  const removeCommodity = (c) => {
    onChange('commodities', value.filter((x) => x !== c));
  };

  return (
    <div>
      <label className="text-[11px] mb-1 block" style={{ color: QB.textSecondary }}>Commodities</label>
      <div className="flex flex-wrap gap-1 mb-1.5">
        {value.map((c, i) => {
          const isUserAdded = !(globalValue || []).includes(c);
          return (
            <span key={i} className="text-[10px] px-1.5 py-0.5 rounded flex items-center gap-1"
              style={{
                backgroundColor: isUserAdded ? QB.purpleLight + '50' : '#F0F1F3',
                color: isUserAdded ? QB.purple : QB.textSecondary,
                border: isUserAdded ? '1px solid ' + QB.purple + '30' : 'none',
              }}>
              {c}
              <button onClick={() => removeCommodity(c)} className="hover:opacity-70"><X size={8} /></button>
            </span>
          );
        })}
      </div>
      <div className="flex gap-1">
        <input
          value={adding}
          onChange={(e) => setAdding(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && addCommodity()}
          placeholder="Add commodity..."
          className="flex-1 px-2 py-1.5 rounded border text-[11px] focus:outline-none"
          style={{ borderColor: QB.cardBorder, color: QB.textPrimary }}
        />
        <button onClick={addCommodity} className="px-2 py-1.5 rounded border text-[11px]"
          style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
          <Plus size={10} />
        </button>
      </div>
      <div className="flex items-center justify-between mt-0.5">
        <div className="text-[10px]" style={{ color: QB.textMuted }}>
          Network: {(globalValue || []).join(', ')}
        </div>
        {hasOverride && (
          <button onClick={() => onReset('commodities')} className="text-[10px] flex items-center gap-0.5" style={{ color: QB.link }}>
            <RotateCcw size={8} /> Reset
          </button>
        )}
      </div>
    </div>
  );
}

function EditTags({ value, onChange }) {
  const [adding, setAdding] = useState('');

  const addTag = () => {
    const trimmed = adding.trim();
    if (trimmed && !value.includes(trimmed)) {
      onChange('tags', [...value, trimmed]);
      setAdding('');
    }
  };

  const removeTag = (t) => {
    onChange('tags', value.filter((x) => x !== t));
  };

  return (
    <div>
      <label className="text-[11px] mb-1 flex items-center gap-1" style={{ color: QB.textSecondary }}>
        Tags <span className="text-[9px] px-1 rounded" style={{ backgroundColor: QB.purpleLight + '40', color: QB.purple }}>native only</span>
      </label>
      <div className="flex flex-wrap gap-1 mb-1.5">
        {value.map((t, i) => (
          <span key={i} className="text-[10px] px-1.5 py-0.5 rounded flex items-center gap-1"
            style={{ backgroundColor: QB.purpleLight + '40', color: QB.purple, border: '1px solid ' + QB.purple + '20' }}>
            {t}
            <button onClick={() => removeTag(t)} className="hover:opacity-70"><X size={8} /></button>
          </span>
        ))}
      </div>
      <div className="flex gap-1">
        <input
          value={adding}
          onChange={(e) => setAdding(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && addTag()}
          placeholder="Add tag..."
          className="flex-1 px-2 py-1.5 rounded border text-[11px] focus:outline-none"
          style={{ borderColor: QB.cardBorder, color: QB.textPrimary }}
        />
        <button onClick={addTag} className="px-2 py-1.5 rounded border text-[11px]"
          style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
          <Plus size={10} />
        </button>
      </div>
    </div>
  );
}

function EntityEditMode({ globalEntity, nativeOverride, onSave, onCancel }) {
  // Initialize draft from existing NATIVE overrides, falling back to GLOBAL values
  const [draft, setDraft] = useState(() => {
    const n = nativeOverride || {};
    const d = {};
    // Initialize all NATIVE_EDITABLE_FIELDS from override → global fallback
    NATIVE_EDITABLE_FIELDS.forEach((f) => {
      const gv = globalEntity[f];
      if (Array.isArray(gv)) {
        d[f] = n[f] ?? [...(gv || [])];
      } else {
        d[f] = n[f] ?? gv ?? '';
      }
    });
    // Native-only fields
    d.nickname = n.nickname ?? '';
    d.notes = n.notes ?? '';
    d.tags = n.tags ?? [];
    return d;
  });

  const update = (field, value) => setDraft((d) => ({ ...d, [field]: value }));

  const resetField = (field) => {
    if (Array.isArray(globalEntity[field])) {
      update(field, [...globalEntity[field]]);
    } else {
      update(field, globalEntity[field] ?? '');
    }
  };

  const handleSave = () => {
    // Build override object: only include fields that differ from GLOBAL
    const overrides = {};
    for (const field of NATIVE_EDITABLE_FIELDS) {
      if (!(field in draft)) continue;
      const globalVal = globalEntity[field];
      const draftVal = draft[field];
      if (Array.isArray(globalVal)) {
        if (JSON.stringify(draftVal) !== JSON.stringify(globalVal)) overrides[field] = draftVal;
      } else {
        if (draftVal !== globalVal) overrides[field] = draftVal;
      }
    }
    // Always include native-only fields if they have content
    if (draft.nickname) overrides.nickname = draft.nickname;
    if (draft.notes) overrides.notes = draft.notes;
    if (draft.tags.length > 0) overrides.tags = draft.tags;

    onSave(globalEntity.id, Object.keys(overrides).length > 0 ? overrides : null);
  };

  const ind = getIndustry(globalEntity.industry);

  return (
    <Widget title="EDIT ENTITY">
      {/* Header context */}
      <div className="flex items-center gap-2 mb-3 pb-2 border-b" style={{ borderColor: QB.cardBorder }}>
        <div className="w-7 h-7 rounded flex items-center justify-center" style={{ backgroundColor: ind.color + '15' }}>
          <Building2 size={13} style={{ color: ind.color }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium truncate" style={{ color: QB.textPrimary }}>{globalEntity.name}</div>
          <div className="text-[10px]" style={{ color: QB.textMuted }}>{ind.label}</div>
        </div>
      </div>

      <div className="text-[10px] mb-3 px-2 py-1.5 rounded" style={{ backgroundColor: QB.purpleLight + '30', color: QB.purple }}>
        Your overrides are visible only to you. They won't affect other users.
      </div>

      <div className="space-y-3">
        {/* Identity */}
        <EditField label="Display name" field="name" value={draft.name} globalValue={globalEntity.name} onChange={update} onReset={resetField} />
        <div className="flex gap-2">
          <div className="flex-1">
            <EditField label="EIN / Tax ID" field="ein" value={draft.ein} globalValue={globalEntity.ein} onChange={update} onReset={resetField} />
          </div>
          <div className="flex-1">
            <EditField label="Contact person" field="contactName" value={draft.contactName} globalValue={globalEntity.contactName} onChange={update} onReset={resetField} />
          </div>
        </div>
        <div className="flex gap-2">
          <div className="flex-1">
            <EditField label="Email" field="email" value={draft.email} globalValue={globalEntity.email} onChange={update} onReset={resetField} />
          </div>
          <div className="flex-1">
            <EditField label="Phone" field="phone" value={draft.phone} globalValue={globalEntity.phone} onChange={update} onReset={resetField} />
          </div>
        </div>
        <EditField label="Website" field="website" value={draft.website} globalValue={globalEntity.website} onChange={update} onReset={resetField} />

        {/* Classification */}
        <EditField label="Legal structure" field="legalStructure" value={draft.legalStructure} globalValue={globalEntity.legalStructure} onChange={update} onReset={resetField} />
        <EditField label="Service area" field="serviceArea" value={draft.serviceArea} globalValue={globalEntity.serviceArea} onChange={update} onReset={resetField} />

        {/* Location */}
        <EditField label="Address" field="address" value={draft.address} globalValue={globalEntity.address} onChange={update} onReset={resetField} />
        <div className="flex gap-2">
          <div className="flex-[2]">
            <EditField label="City" field="city" value={draft.city} globalValue={globalEntity.city} onChange={update} onReset={resetField} />
          </div>
          <div className="flex-1">
            <EditField label="State" field="state" value={draft.state} globalValue={globalEntity.state} onChange={update} onReset={resetField} />
          </div>
          <div className="flex-1">
            <EditField label="ZIP" field="zip" value={draft.zip} globalValue={globalEntity.zip} onChange={update} onReset={resetField} />
          </div>
        </div>

        <EditCommodities value={draft.commodities} globalValue={globalEntity.commodities} onChange={update} onReset={resetField} />

        {/* Divider */}
        <div className="border-t pt-3" style={{ borderColor: QB.cardBorder }}>
          <div className="text-[10px] font-semibold tracking-wider mb-2 flex items-center gap-1"
            style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
            <Tag size={9} /> NATIVE ONLY
          </div>
        </div>

        {/* NATIVE-only fields */}
        <div>
          <label className="text-[11px] mb-1 flex items-center gap-1" style={{ color: QB.textSecondary }}>
            Nickname <span className="text-[9px] px-1 rounded" style={{ backgroundColor: QB.purpleLight + '40', color: QB.purple }}>native only</span>
          </label>
          <input
            value={draft.nickname}
            onChange={(e) => update('nickname', e.target.value)}
            placeholder="Your name for this entity..."
            className="w-full px-2.5 py-2 rounded border text-xs focus:outline-none"
            style={{ borderColor: QB.cardBorder, color: QB.textPrimary }}
          />
        </div>

        <div>
          <label className="text-[11px] mb-1 flex items-center gap-1" style={{ color: QB.textSecondary }}>
            Notes <span className="text-[9px] px-1 rounded" style={{ backgroundColor: QB.purpleLight + '40', color: QB.purple }}>native only</span>
          </label>
          <textarea
            value={draft.notes}
            onChange={(e) => update('notes', e.target.value)}
            placeholder="Private notes about this entity..."
            rows={2}
            className="w-full px-2.5 py-2 rounded border text-xs focus:outline-none resize-none"
            style={{ borderColor: QB.cardBorder, color: QB.textPrimary }}
          />
        </div>

        <EditTags value={draft.tags} onChange={update} />
      </div>

      {/* Save / Cancel */}
      <div className="flex gap-2 mt-4">
        <button onClick={onCancel}
          className="flex-1 text-xs py-2 rounded border transition-colors hover:bg-gray-50"
          style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
          Cancel
        </button>
        <button onClick={handleSave}
          className="flex-1 text-xs py-2 rounded text-white flex items-center justify-center gap-1.5 transition-colors"
          style={{ backgroundColor: QB.green }}>
          <Check size={11} /> Save changes
        </button>
      </div>
    </Widget>
  );
}

// ── View mode (existing) ────────────────────────────────

function EntityViewMode({
  globalEntity, nativeOverride, entity, onOpenAI, onEdit, onMerge,
  onSelectEntity, onTraceSupplyChain, onShowOnNetwork, vendorRels, clientRels, allEntities,
}) {
  const [showProfile, setShowProfile] = useState(false);

  useEffect(() => { setShowProfile(false); }, [globalEntity?.id]);

  const hasNativeOverrides = nativeOverride && Object.keys(nativeOverride).length > 0;
  const ind = getIndustry(entity.industry);

  const ProfileField = ({ label, field, value }) => {
    const isNative = isNativeOverride(entity, field);
    const globalVal = isNative ? getGlobalValue(globalEntity, field) : null;
    return (
      <div className="text-xs">
        <div className="flex items-center gap-1">
          <span style={{ color: QB.textMuted }}>{label}: </span>
          <span style={{ color: QB.textPrimary }}>{value}</span>
          {isNative && <NativeBadge />}
        </div>
        {isNative && globalVal != null && (
          <GlobalFallback value={Array.isArray(globalVal) ? globalVal.join(', ') : String(globalVal)} />
        )}
      </div>
    );
  };

  return (
    <>
      <Widget
        title="SELECTED ENTITY"
        action={
          <button onClick={() => setShowProfile(!showProfile)} className="text-[10px]" style={{ color: QB.link }}>
            {showProfile ? 'Less' : 'Full profile'} {showProfile ? '\u25B4' : '\u25BE'}
          </button>
        }
      >
        {/* Header row */}
        <div className="flex items-center gap-3 mb-3">
          <div className="w-9 h-9 rounded flex items-center justify-center" style={{ backgroundColor: ind.color + '15' }}>
            <Building2 size={16} style={{ color: ind.color }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <div className="text-sm font-medium truncate" style={{ color: QB.textPrimary }}>{entity.name}</div>
              {isNativeOverride(entity, 'name') && <NativeBadge />}
            </div>
            <div className="text-[11px]" style={{ color: QB.textMuted }}>
              {ind.label} &middot; {entity.city}, {entity.state}
              {(isNativeOverride(entity, 'city') || isNativeOverride(entity, 'state')) && (
                <> <NativeBadge /></>
              )}
            </div>
          </div>
        </div>

        {/* Nickname */}
        {entity.nickname && (
          <div className="flex items-center gap-1.5 mb-2 px-2 py-1 rounded text-[11px]" style={{ backgroundColor: QB.purpleLight + '40', color: QB.purple }}>
            <Tag size={10} />
            <span>"{entity.nickname}"</span>
            <NativeBadge />
          </div>
        )}

        {/* Stats grid */}
        <div className="grid grid-cols-3 gap-2 mb-3">
          {[
            { l: 'Vendors', v: entity.vendors, c: QB.purple },
            { l: 'Clients', v: entity.clients, c: QB.green },
            { l: 'Volume', v: fmt(entity.volume), c: QB.link },
          ].map((s, i) => (
            <div key={i} className="text-center py-2 rounded" style={{ backgroundColor: '#F4F5F7' }}>
              <div className="text-sm font-semibold" style={{ color: s.c }}>{s.v}</div>
              <div className="text-[10px]" style={{ color: QB.textMuted }}>{s.l}</div>
            </div>
          ))}
        </div>

        {/* Expanded profile */}
        {showProfile && (
          <div className="space-y-2.5 pt-2 border-t" style={{ borderColor: QB.cardBorder }}>
            <div className="flex items-center justify-between">
              <div className="text-[10px] font-semibold tracking-wider" style={{ color: QB.textMuted, letterSpacing: '0.08em' }}>
                ENTITY PERSONA
              </div>
              {hasNativeOverrides && (
                <span className="text-[9px] px-1.5 py-0.5 rounded flex items-center gap-1" style={{ backgroundColor: QB.purpleLight + '40', color: QB.purple }}>
                  <NativeBadge /> = your override
                </span>
              )}
            </div>

            {/* Identification */}
            {entity.ein && <ProfileField label="EIN / Tax ID" field="ein" value={entity.ein} />}
            {entity.contactName && <ProfileField label="Contact" field="contactName" value={entity.contactName} />}
            {entity.email && <ProfileField label="Email" field="email" value={entity.email} />}
            {entity.phone && <ProfileField label="Phone" field="phone" value={entity.phone} />}
            {entity.website && <ProfileField label="Website" field="website" value={entity.website} />}

            {/* Classification */}
            <ProfileField label="Legal structure" field="legalStructure" value={entity.legalStructure} />
            <ProfileField label="NAICS code" field="naics" value={entity.naics + ' \u2014 ' + ind.label} />
            <ProfileField label="Service area" field="serviceArea" value={entity.serviceArea} />

            {/* Location */}
            {entity.address && <ProfileField label="Address" field="address" value={entity.address} />}
            {entity.zip && <ProfileField label="ZIP" field="zip" value={entity.zip} />}

            <ProfileField label="Name variants" field="variants" value={(entity.variants || []).map((v) => '"' + v + '"').join(', ')} />

            {/* Commodities */}
            <div className="text-xs">
              <div className="flex items-center gap-1">
                <span style={{ color: QB.textMuted }}>Commodities: </span>
                {isNativeOverride(entity, 'commodities') && <NativeBadge />}
              </div>
              <div className="flex flex-wrap gap-1 mt-1">
                {(entity.commodities || []).map((c, i) => {
                  const isUserAdded = nativeOverride?.commodities?.includes(c) &&
                    !(globalEntity.commodities || []).includes(c);
                  return (
                    <span key={i} className="text-[10px] px-1.5 py-0.5 rounded flex items-center gap-0.5"
                      style={{
                        backgroundColor: isUserAdded ? QB.purpleLight + '50' : '#F0F1F3',
                        color: isUserAdded ? QB.purple : QB.textSecondary,
                        border: isUserAdded ? '1px solid ' + QB.purple + '30' : 'none',
                      }}>
                      {c}
                      {isUserAdded && <span className="text-[7px] font-bold">n</span>}
                    </span>
                  );
                })}
              </div>
              {isNativeOverride(entity, 'commodities') && (
                <GlobalFallback value={(globalEntity.commodities || []).join(', ')} />
              )}
            </div>

            {/* Notes */}
            {entity.notes && (
              <div className="text-xs">
                <div className="flex items-center gap-1">
                  <StickyNote size={10} style={{ color: QB.textMuted }} />
                  <span style={{ color: QB.textMuted }}>Notes: </span>
                  <NativeBadge />
                </div>
                <div className="mt-0.5 px-2 py-1 rounded text-[11px]" style={{ backgroundColor: '#FAFAFA', color: QB.textSecondary }}>
                  {entity.notes}
                </div>
              </div>
            )}

            {/* Tags */}
            {entity.tags && entity.tags.length > 0 && (
              <div className="text-xs">
                <div className="flex items-center gap-1 mb-1">
                  <span style={{ color: QB.textMuted }}>Tags: </span>
                  <NativeBadge />
                </div>
                <div className="flex flex-wrap gap-1">
                  {entity.tags.map((t, i) => (
                    <span key={i} className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{ backgroundColor: QB.purpleLight + '40', color: QB.purple, border: '1px solid ' + QB.purple + '20' }}>
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-2 mt-3">
          <button onClick={onEdit}
            className="flex-1 text-xs py-2 rounded flex items-center justify-center gap-1.5 border transition-colors hover:bg-gray-50"
            style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
            <Pencil size={11} /> Edit
          </button>
          <button onClick={() => onMerge?.(entity, globalEntity)}
            className="flex-1 text-xs py-2 rounded flex items-center justify-center gap-1.5 border transition-colors hover:bg-gray-50"
            style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
            <GitMerge size={11} /> Merge into...
          </button>
        </div>
        <button onClick={() => onOpenAI?.(entity)}
          className="w-full text-xs py-2 rounded flex items-center justify-center gap-1.5 mt-1"
          style={{ backgroundColor: QB.greenLight, color: QB.greenDark }}>
          <Sparkles size={11} /> Ask Intuit Assist
        </button>
        {onShowOnNetwork && (
          <button onClick={() => onShowOnNetwork(entity)}
            className="w-full text-xs py-2 rounded flex items-center justify-center gap-1.5 mt-1 border transition-colors hover:bg-gray-50"
            style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
            <Share2 size={11} /> Show on Network
          </button>
        )}
        {onTraceSupplyChain && (
          <button onClick={() => onTraceSupplyChain(entity)}
            className="w-full text-xs py-2 rounded flex items-center justify-center gap-1.5 mt-1 border transition-colors hover:bg-gray-50"
            style={{ borderColor: QB.cardBorder, color: QB.textSecondary }}>
            <Network size={11} /> Trace supply chain
          </button>
        )}
      </Widget>

      {/* Vendors list */}
      {vendorRels.length > 0 && (
        <Widget title={'VENDORS (' + vendorRels.length + ')'}>
          <div className="space-y-1.5">
            {vendorRels.slice(0, 4).map((rel, i) => {
              const o = allEntities.find((e) => e.id === (rel.source === globalEntity.id ? rel.target : rel.source));
              return (
                <div key={i} className="flex items-center gap-2 text-xs py-1.5 border-b cursor-pointer hover:bg-gray-50 -mx-1 px-1 rounded"
                  style={{ borderColor: '#F0F0F0' }} onClick={() => o && onSelectEntity?.(o)}>
                  <span className="text-[10px] px-1 py-0.5 rounded font-medium" style={{ backgroundColor: QB.purpleLight, color: QB.purpleDark }}>{'\u2190'} V</span>
                  <span className="flex-1 truncate" style={{ color: QB.textPrimary }}>{o?.name}</span>
                  {rel.status === 'dormant' && <span className="text-[9px] px-1 rounded" style={{ backgroundColor: '#F0F0F0', color: QB.dormant }}>dormant</span>}
                  <span style={{ color: QB.textMuted }}>{fmt(rel.volume)}</span>
                </div>
              );
            })}
          </div>
        </Widget>
      )}

      {/* Clients list */}
      {clientRels.length > 0 && (
        <Widget title={'CLIENTS (' + clientRels.length + ')'}>
          <div className="space-y-1.5">
            {clientRels.slice(0, 4).map((rel, i) => {
              const o = allEntities.find((e) => e.id === (rel.source === globalEntity.id ? rel.target : rel.source));
              return (
                <div key={i} className="flex items-center gap-2 text-xs py-1.5 border-b cursor-pointer hover:bg-gray-50 -mx-1 px-1 rounded"
                  style={{ borderColor: '#F0F0F0' }} onClick={() => o && onSelectEntity?.(o)}>
                  <span className="text-[10px] px-1 py-0.5 rounded font-medium" style={{ backgroundColor: QB.greenLight, color: QB.greenDark }}>{'\u2192'} C</span>
                  <span className="flex-1 truncate" style={{ color: QB.textPrimary }}>{o?.name}</span>
                  {rel.status === 'dormant' && <span className="text-[9px] px-1 rounded" style={{ backgroundColor: '#F0F0F0', color: QB.dormant }}>dormant</span>}
                  <span style={{ color: QB.textMuted }}>{fmt(rel.volume)}</span>
                </div>
              );
            })}
          </div>
        </Widget>
      )}
    </>
  );
}

// ── Main component ──────────────────────────────────────

/**
 * Perspective-aware entity detail panel with inline edit mode.
 *
 * Props:
 *  - globalEntity: the raw GLOBAL golden record
 *  - nativeOverride: the user's NATIVE overrides for this entity (or null)
 *  - onSaveNative: (entityId, overrides) => void — persist native overrides (null to clear all)
 *  - onOpenAI: callback to open Intuit Assist
 *  - onMerge: callback when "Merge Into..." is clicked
 *  - onSelectEntity: callback to navigate to another entity
 *  - vendorRels / clientRels: pre-filtered relationship arrays
 *  - allEntities: all entities for name lookups
 */
export function EntityDetailPanel({
  globalEntity,
  nativeOverride,
  onSaveNative,
  onOpenAI,
  onMerge,
  onSelectEntity,
  onTraceSupplyChain,
  onShowOnNetwork,
  vendorRels = [],
  clientRels = [],
  allEntities = [],
}) {
  const [editing, setEditing] = useState(false);
  const entity = resolveEntity(globalEntity, nativeOverride);

  // Exit edit mode when entity changes
  useEffect(() => { setEditing(false); }, [globalEntity?.id]);

  if (!entity) return null;

  const handleSave = (entityId, overrides) => {
    onSaveNative?.(entityId, overrides);
    setEditing(false);
  };

  if (editing) {
    return (
      <EntityEditMode
        globalEntity={globalEntity}
        nativeOverride={nativeOverride}
        onSave={handleSave}
        onCancel={() => setEditing(false)}
      />
    );
  }

  return (
    <EntityViewMode
      globalEntity={globalEntity}
      nativeOverride={nativeOverride}
      entity={entity}
      onOpenAI={onOpenAI}
      onEdit={() => setEditing(true)}
      onMerge={onMerge}
      onSelectEntity={onSelectEntity}
      onTraceSupplyChain={onTraceSupplyChain}
      onShowOnNetwork={onShowOnNetwork}
      vendorRels={vendorRels}
      clientRels={clientRels}
      allEntities={allEntities}
    />
  );
}
