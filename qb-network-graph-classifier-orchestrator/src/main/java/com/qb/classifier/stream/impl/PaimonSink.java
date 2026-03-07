package com.qb.classifier.stream.impl;

import com.fasterxml.jackson.databind.JsonNode;
import com.qb.classifier.config.Config;
import com.qb.classifier.stream.ResolvedEntitySink;
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
 * Implements {@link ResolvedEntitySink} for DI.
 */
public class PaimonSink implements ResolvedEntitySink {

    private static final Logger log = LoggerFactory.getLogger(PaimonSink.class);

    private final Table goldenRecordsTable;
    private final Table relationshipsTable;
    private final Table auditTable;
    private final Table pendingResolutionTable;
    private boolean available;

    public PaimonSink(Config config) {
        Table gr = null, rel = null, aud = null, pr = null;
        try {
            Options options = new Options();
            options.set("warehouse", config.warehousePath);
            options.set("commit.force-create-snapshot", "true");
            CatalogContext ctx = CatalogContext.create(options);
            Catalog catalog = CatalogFactory.createCatalog(ctx);

            gr = catalog.getTable(Identifier.create("gold", "golden_records"));
            rel = catalog.getTable(Identifier.create("gold", "relationships"));
            aud = catalog.getTable(Identifier.create("gold", "resolution_audit"));
            this.available = true;
            log.info("PaimonSink connected to gold.golden_records, gold.relationships, gold.resolution_audit");
        } catch (Exception e) {
            log.warn("Paimon gold tables not available ({}). Gold writes disabled.", e.getMessage());
            this.available = false;
        }
        try {
            if (available) {
                Options options = new Options();
                options.set("warehouse", config.warehousePath);
                CatalogContext ctx = CatalogContext.create(options);
                Catalog catalog = CatalogFactory.createCatalog(ctx);
                pr = catalog.getTable(Identifier.create("gold", "pending_resolution"));
                log.info("PaimonSink connected to gold.pending_resolution");
            }
        } catch (Exception e) {
            log.warn("gold.pending_resolution not available ({}). Pending writes disabled.", e.getMessage());
        }
        this.goldenRecordsTable = gr;
        this.relationshipsTable = rel;
        this.auditTable = aud;
        this.pendingResolutionTable = pr;
    }

    @Override
    public boolean isAvailable() {
        return available;
    }

    @Override
    public void writeGoldenRecord(JsonNode gr) {
        if (!available || gr == null || gr.isNull()) return;
        try {
            BatchTableWrite write = goldenRecordsTable.newBatchWriteBuilder().newWrite();
            BatchTableCommit commit = goldenRecordsTable.newBatchWriteBuilder().newCommit();

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
                Timestamp.now(),
                Timestamp.now()
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

    @Override
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
                Timestamp.now(),
                Timestamp.now()
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

    @Override
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
                Timestamp.now()
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

    @Override
    public void writePendingResolution(JsonNode pr) {
        if (!available || pendingResolutionTable == null || pr == null || pr.isNull()) return;
        try {
            BatchTableWrite write = pendingResolutionTable.newBatchWriteBuilder().newWrite();
            BatchTableCommit commit = pendingResolutionTable.newBatchWriteBuilder().newCommit();

            GenericRow row = GenericRow.of(
                str(pr, "match_id"),
                str(pr, "orphan_golden_id"),
                str(pr, "candidate_golden_id"),
                decimal(pr, "confidence", 4, 3),
                jsonStr(pr, "dimension_scores"),
                str(pr, "reasoning"),
                str(pr, "key_uncertainty"),
                str(pr, "trigger_type"),
                BinaryString.fromString("PENDING"),
                null,   // reviewer
                null,   // reviewed_at
                Timestamp.now()
            );

            write.write(row);
            List<CommitMessage> messages = write.prepareCommit();
            commit.commit(messages);
            write.close();
            commit.close();

            log.debug("Wrote pending_resolution {} to Paimon gold", textVal(pr, "match_id"));
        } catch (Exception e) {
            log.error("Failed to write pending_resolution to Paimon gold: {}", e.getMessage());
        }
    }

    // ── Type conversion helpers ──────────────────────────────

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
