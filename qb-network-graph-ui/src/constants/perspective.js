/**
 * Perspective model — defines how GLOBAL (network) and NATIVE (user) data layers interact.
 *
 * GLOBAL: system-managed golden records visible to all users.
 * NATIVE: user-specific overrides, annotations, and merges.
 * The user always sees NATIVE on top of GLOBAL (NATIVE wins where it has a value).
 */

export const PERSPECTIVE = {
  GLOBAL: 'global',
  NATIVE: 'native',
};

/** Fields the user can override with their own values (shows GLOBAL underneath). */
export const NATIVE_EDITABLE_FIELDS = [
  // Identity
  'name',
  'ein',
  'contactName',
  'email',
  'phone',
  'website',
  // Classification
  'industry',
  'naics',
  'legalStructure',
  // Location
  'address',
  'city',
  'state',
  'zip',
  // Business details
  'commodities',
  'serviceArea',
  'variants',
];

/** Fields that exist only in the NATIVE layer (no GLOBAL counterpart). */
export const NATIVE_ONLY_FIELDS = [
  'nickname',
  'notes',
  'tags',
];

/** Merge action provenance — who initiated the merge. */
export const MERGE_ORIGIN = {
  SYSTEM: 'system',
  USER: 'user',
};

/** Merge resolution outcomes. */
export const MERGE_RESOLUTION = {
  MERGED: 'merged',
  REJECTED: 'rejected',
  UNDONE: 'undone',
};
