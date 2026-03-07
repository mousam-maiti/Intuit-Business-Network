import { PERSPECTIVE, NATIVE_EDITABLE_FIELDS, NATIVE_ONLY_FIELDS } from '@/constants/perspective';

/**
 * Resolve a GLOBAL entity with NATIVE overrides into a composite entity.
 * NATIVE wins where it has a value; GLOBAL shows through everywhere else.
 *
 * Returns:
 *   { ...compositeFields, _perspective: { fieldName: 'global'|'native', ... } }
 *
 * The _perspective map lets the UI know which fields are overridden,
 * so it can render ⓝ badges and "Reset to network value" controls.
 */
export function resolveEntity(globalEntity, nativeOverride) {
  if (!globalEntity) return null;

  const composite = { ...globalEntity };
  const perspectiveMap = {};

  // Mark all base fields as GLOBAL
  for (const key of Object.keys(globalEntity)) {
    perspectiveMap[key] = PERSPECTIVE.GLOBAL;
  }

  // Ensure every NATIVE_EDITABLE_FIELD is in the perspective map even if
  // the global entity doesn't carry it yet (e.g. ein, phone, website …)
  for (const field of NATIVE_EDITABLE_FIELDS) {
    if (!(field in perspectiveMap)) {
      perspectiveMap[field] = PERSPECTIVE.GLOBAL;
    }
  }

  // Apply NATIVE overrides on editable fields
  if (nativeOverride) {
    for (const field of NATIVE_EDITABLE_FIELDS) {
      if (field in nativeOverride && nativeOverride[field] != null) {
        composite[field] = nativeOverride[field];
        perspectiveMap[field] = PERSPECTIVE.NATIVE;
      }
    }

    // Apply NATIVE-only fields (no GLOBAL counterpart)
    for (const field of NATIVE_ONLY_FIELDS) {
      if (field in nativeOverride) {
        composite[field] = nativeOverride[field];
        perspectiveMap[field] = PERSPECTIVE.NATIVE;
      }
    }
  }

  composite._perspective = perspectiveMap;
  return composite;
}

/**
 * Get the GLOBAL (original) value for a field, even when NATIVE has overridden it.
 * Useful for showing "Network: 100 Main St, Phoenix AZ" under a NATIVE override.
 */
export function getGlobalValue(globalEntity, field) {
  if (!globalEntity) return undefined;
  return globalEntity[field];
}

/**
 * Check if a specific field is overridden by the NATIVE perspective.
 */
export function isNativeOverride(compositeEntity, field) {
  return compositeEntity?._perspective?.[field] === PERSPECTIVE.NATIVE;
}

/**
 * Get all fields that have NATIVE overrides on a composite entity.
 * Returns array of field names.
 */
export function getNativeFields(compositeEntity) {
  if (!compositeEntity?._perspective) return [];
  return Object.entries(compositeEntity._perspective)
    .filter(([, p]) => p === PERSPECTIVE.NATIVE)
    .map(([field]) => field);
}

/**
 * Apply native merges to a list of entities and relationships.
 * For each native merge, the source entity is hidden and its
 * relationships are remapped to the target entity.
 *
 * Returns { entities, relationships } with merges applied.
 */
export function applyNativeMerges(entities, relationships, nativeMerges) {
  if (!nativeMerges || nativeMerges.length === 0) {
    return { entities, relationships };
  }

  const mergedSourceIds = new Set(nativeMerges.map((m) => m.sourceEntityId));
  const mergeTargetMap = {};
  for (const m of nativeMerges) {
    mergeTargetMap[m.sourceEntityId] = m.targetEntityId;
  }

  // Hide merged source entities
  const filteredEntities = entities.filter((e) => !mergedSourceIds.has(e.id));

  // Remap relationships: replace source entity refs with target
  const remappedRelationships = relationships.map((r) => {
    const newSource = mergeTargetMap[r.source] || r.source;
    const newTarget = mergeTargetMap[r.target] || r.target;
    // Skip self-loops created by merge
    if (newSource === newTarget) return null;
    if (newSource !== r.source || newTarget !== r.target) {
      return { ...r, source: newSource, target: newTarget, _mergeRemapped: true };
    }
    return r;
  }).filter(Boolean);

  return { entities: filteredEntities, relationships: remappedRelationships };
}
