import { apiClient } from './client';
import { config } from '@/config/env';
import {
  mockGetNativeOverrides, mockGetNativeOverride,
  mockSaveNativeOverride, mockDeleteNativeOverride,
  mockGetNativeMerges, mockCreateNativeMerge, mockUndoNativeMerge,
} from './mock/handlers';

// ── Attribute Overrides ─────────────────────────────────

/** Get all native overrides for the current user. */
export async function getNativeOverrides() {
  if (config.flags.useMocks) return mockGetNativeOverrides();
  return apiClient.get('/native/overrides');
}

/** Get native overrides for a single entity. */
export async function getNativeOverride(entityId) {
  if (config.flags.useMocks) return mockGetNativeOverride(entityId);
  return apiClient.get(`/native/overrides/${entityId}`);
}

/** Save (create or update) native overrides for an entity. Merges with existing. */
export async function saveNativeOverride(entityId, fields) {
  if (config.flags.useMocks) return mockSaveNativeOverride(entityId, fields);
  return apiClient.patch(`/native/overrides/${entityId}`, fields);
}

/** Remove a single field override, resetting it to the GLOBAL value. */
export async function deleteNativeOverride(entityId, field) {
  if (config.flags.useMocks) return mockDeleteNativeOverride(entityId, field);
  return apiClient.delete(`/native/overrides/${entityId}/${field}`);
}

// ── Native Merges ───────────────────────────────────────

/** Get all native merges for the current user. */
export async function getNativeMerges() {
  if (config.flags.useMocks) return mockGetNativeMerges();
  return apiClient.get('/native/merges');
}

/** Create a user-driven native merge. */
export async function createNativeMerge(payload) {
  if (config.flags.useMocks) return mockCreateNativeMerge(payload);
  return apiClient.post('/native/merges', payload);
}

/** Undo a native merge, restoring the source entity and its relationships. */
export async function undoNativeMerge(mergeId) {
  if (config.flags.useMocks) return mockUndoNativeMerge(mergeId);
  return apiClient.delete(`/native/merges/${mergeId}`);
}
