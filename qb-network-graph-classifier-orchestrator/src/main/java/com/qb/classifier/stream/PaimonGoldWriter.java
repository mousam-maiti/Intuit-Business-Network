package com.qb.classifier.stream;

import com.fasterxml.jackson.databind.JsonNode;
import com.qb.classifier.config.Config;
import org.apache.paimon.catalog.Catalog;
import org.apache.paimon.catalog.CatalogContext;
import org.apache.paimon.catalog.CatalogFactory;
import org.apache.paimon.catalog.Identifier;
import org.apache.paimon.data.BinaryString;
import org.apache.paimon.data.Decimal;
import org.apache.paimon.data.GenericRow;
import org.apache.paimon.data.Timestamp;
import org.apache.paimon.options.Options;
import org.apache.paimon.table.Table;
import org.apache.paimon.table.sink.BatchTableCommit;
import org.apache.paimon.table.sink.BatchTableWrite;
import org.apache.paimon.table.sink.CommitMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.math.BigDecimal;
import java.util.List;

/**
 * Writes resolved entity data to Paimon gold layer tables.
 *
 * Three tables:
 *   - gold.golden_records   (30+ columns, UPSERT via deduplicate merge engine)
 *   - gold.relationships    (directed edges)
 *   - gold.resolution_audit (append-only audit trail)
 *
 * Called by App after each successful /resolve response.
 * Uses Paimon's batch write API (same pattern as PaimonConsumer reads).
 */
public class PaimonGoldWriter {

    private static final Logger log = LoggerFactory.getLogger(PaimonGoldWriter.class);
    private static final String COMMIT_USER = "classifier-orchestrator";

    private final Table goldenRecordsTable;
    private final Table relationshipsTable;
    private final Table auditTable;
    private boolean available;

    public PaimonGoldWriter(Config config) {
        Table gr = null, rel = null, aud = null;
        try {
            Options options = new Options();
            options.set("warehouse", config.warehousePath);
            CatalogContext ctx = CatalogContext.create(options);
            Catalog catalog = CatalogFactory.createCatalog(ctx);

            gr = catalog.getTable(Identifier.create("gold", "golden_records"));
            rel = catalog.getTable(Identifier.create("gold", "relationships"));
            aud = catalog.getTable(Identifier.create("gold", "resolution_audit"));
            this.available = true;
            log.info("PaimonGoldWriter connected to gold.golden_records, gold.relationships, gold.resolution_audit");
        } catch (Exception e) {
            log.warn("Paimon gold tables not available ({}). Gold writes disabled — Neo4j is primary.", e.getMessage());
            this.available = false;
        }
        this.goldenRecordsTable = gr;
        this.relationshipsTable = rel;
        this.auditTable = aud;
    }

    public boolean isAvailable() {
        return available;
    }

    /**
     * Write a golden record to gold.golden_records.
     * Called after each /resolve response that returns a golden_record_after.
     */
    public void writeGoldenRecord(JsonNode gr) {
        if (!available || gr == null || gr.isNull()) return;
        try {
            BatchTableWrite write = goldenRecordsTable.newBatchWriteBuilder().newWrite();
            BatchTableCommit commit = goldenRecordsTable.newBatchWriteBuilder().newCommit();

            // 32 columns matching 06-paimon-gold-tables.sql
            GenericRow row = GenericRow.of(
                str(gr, "golden_record_id"),
                str(gr, "canonical_name"),
                jsonStr(gr, "name_variants"),
                str(gr, "ein"),
                str(gr, "phone_digits"),
                str(gr, "email"),
                str(gr, "email_domain"),
                str(gr, "contact_name"),
                str(gr, "naics_code"),
                str(gr, "naics_sector"),
                str(gr, "naics_subsector"),
                str(gr, "state"),
                str(gr, "city"),
                str(gr, "zip5"),
                str(gr, "zip3"),
                str(gr, "street_address"),
                jsonStr(gr, "commodity_keywords"),
                jsonStr(gr, "service_categories"),
                decimal(gr, "total_volume", 14, 2),
                decimal(gr, "avg_transaction", 12, 2),
                intVal(gr, "transaction_count"),
                str(gr, "volume_bracket"),
                intVal(gr, "source_count"),
                jsonStr(gr, "source_records"),
                decimal(gr, "confidence", 4, 3),
                str(gr, "status"),
                str(gr, "merged_into"),
                str(gr, "entity_type"),
                jsonStr(gr, "persona"),
                jsonStr(gr, "bucket_keys"),
                Timestamp.now(),  // created_at
                Timestamp.now()   // updated_at
            );

            write.write(row);
            List<CommitMessage> messages = write.prepareCommit();
            commit.commit(messages);
            write.close();
            commit.close();

            log.debug("Wrote golden_record {} to Paimon gold", textVal(gr, "golden_record_id"));
        } catch (Exception e) {
            log.error("Failed to write golden record to Paimon gold: {}", e.getMessage());
        }
    }

    /**
     * Write a relationship to gold.relationships.
     */
    public void writeRelationship(JsonNode rel) {
        if (!available || rel == null || rel.isNull()) return;
        try {
            BatchTableWrite write = relationshipsTable.newBatchWriteBuilder().newWrite();
            BatchTableCommit commit = relationshipsTable.newBatchWriteBuilder().newCommit();

            GenericRow row = GenericRow.of(
                str(rel, "edge_id"),
                str(rel, "source_entity_id"),
                str(rel, "target_entity_id"),
                str(rel, "rel_type"),
                decimal(rel, "transaction_volume", 14, 2),
                intVal(rel, "transaction_count"),
                Timestamp.now(),  // created_at
                Timestamp.now()   // updated_at
            );

            write.write(row);
            List<CommitMessage> messages = write.prepareCommit();
            commit.commit(messages);
            write.close();
            commit.close();

            log.debug("Wrote relationship {} to Paimon gold", textVal(rel, "edge_id"));
        } catch (Exception e) {
            log.error("Failed to write relationship to Paimon gold: {}", e.getMessage());
        }
    }

    /**
     * Write an audit entry to gold.resolution_audit.
     */
    public void writeAudit(JsonNode audit) {
        if (!available || audit == null || audit.isNull()) return;
        try {
            BatchTableWrite write = auditTable.newBatchWriteBuilder().newWrite();
            BatchTableCommit commit = auditTable.newBatchWriteBuilder().newCommit();

            GenericRow row = GenericRow.of(
                str(audit, "audit_id"),
                str(audit, "event_id"),
                str(audit, "record_id"),
                str(audit, "perspective"),
                str(audit, "decision"),
                str(audit, "trigger_type"),
                str(audit, "target_golden_id"),
                str(audit, "absorbed_golden_id"),
                decimal(audit, "confidence", 4, 3),
                jsonStr(audit, "dimension_scores"),
                str(audit, "reasoning"),
                jsonStr(audit, "key_factors"),
                intVal(audit, "candidates_evaluated"),
                intVal(audit, "llm_calls"),
                intVal(audit, "embedding_calls"),
                intVal(audit, "total_duration_ms"),
                jsonStr(audit, "evaluation_chain"),
                jsonStr(audit, "golden_record_before"),
                jsonStr(audit, "golden_record_after"),
                Timestamp.now()   // created_at
            );

            write.write(row);
            List<CommitMessage> messages = write.prepareCommit();
            commit.commit(messages);
            write.close();
            commit.close();

            log.debug("Wrote audit {} to Paimon gold", textVal(audit, "audit_id"));
        } catch (Exception e) {
            log.error("Failed to write audit to Paimon gold: {}", e.getMessage());
        }
    }

    // ── Type conversion helpers ─────────────────────────────

    private static BinaryString str(JsonNode node, String field) {
        String val = textVal(node, field);
        return val != null ? BinaryString.fromString(val) : null;
    }

    private static BinaryString jsonStr(JsonNode node, String field) {
        JsonNode child = node.get(field);
        if (child == null || child.isNull()) return null;
        if (child.isTextual()) return BinaryString.fromString(child.asText());
        return BinaryString.fromString(child.toString());
    }

    private static String textVal(JsonNode node, String field) {
        JsonNode child = node.get(field);
        if (child == null || child.isNull()) return null;
        return child.asText();
    }

    private static Decimal decimal(JsonNode node, String field, int precision, int scale) {
        JsonNode child = node.get(field);
        if (child == null || child.isNull()) return null;
        return Decimal.fromBigDecimal(new BigDecimal(child.asText()), precision, scale);
    }

    private static Integer intVal(JsonNode node, String field) {
        JsonNode child = node.get(field);
        if (child == null || child.isNull()) return null;
        return child.asInt();
    }
}
