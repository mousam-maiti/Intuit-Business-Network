import { apiClient } from './client';

/** Get list of entities that have lineage data. */
export async function getLineageEntities() {
  return apiClient.get('/lineage/entities');
}

/** Get all audit trail entries for an entity, sorted by date ascending. */
export async function getEntityAuditTrail(entityId, limit = 100) {
  return apiClient.get(`/lineage/trail/${entityId}`, { params: { limit } });
}

/**
 * Reconstruct an entity's golden record state at a specific date.
 * Returns the last golden_record_after before the given date.
 */
export async function getEntitySnapshot(entityId, date) {
  return apiClient.get(`/lineage/snapshot/${entityId}`, { params: { date } });
}

/** Restore an entity to a previous golden record state from an audit entry. */
export async function restoreEntity(entityId, auditId, snapshot) {
  return apiClient.post(`/lineage/restore/${entityId}`, { audit_id: auditId, snapshot });
}
