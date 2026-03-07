package com.qb.classifier.stream;

import com.qb.classifier.config.Config;
import com.qb.classifier.model.EntityConnection;
import org.apache.paimon.catalog.Catalog;
import org.apache.paimon.catalog.CatalogContext;
import org.apache.paimon.catalog.CatalogFactory;
import org.apache.paimon.catalog.Identifier;
import org.apache.paimon.data.InternalRow;
import org.apache.paimon.data.BinaryString;
import org.apache.paimon.data.Decimal;
import org.apache.paimon.options.Options;
import org.apache.paimon.reader.RecordReader;
import org.apache.paimon.table.Table;
import org.apache.paimon.table.source.*;
import org.apache.paimon.types.DataField;
import org.apache.paimon.types.RowType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Instant;
import java.time.ZoneId;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

/**
 * Reads entity_connections from Paimon using the Java API.
 *
 * Two modes:
 *   - batch:  Full snapshot read -> process all rows -> exit
 *   - stream: StreamTableScan with checkpoint/restore -> tails changelog
 */
public class PaimonConsumer {

    private static final Logger log = LoggerFactory.getLogger(PaimonConsumer.class);

    private final Config config;
    private final Table table;
    private final Path checkpointPath;

    /** Column name -> positional index, resolved from the table schema at startup. */
    private final Map<String, Integer> columnIndex;

    public PaimonConsumer(Config config) throws Exception {
        this.config = config;

        // Create catalog
        Options options = new Options();
        options.set("warehouse", config.warehousePath);
        CatalogContext ctx = CatalogContext.create(options);
        Catalog catalog = CatalogFactory.createCatalog(ctx);

        // Get table
        Identifier tableId = Identifier.create(config.database, config.sourceTable);
        this.table = catalog.getTable(tableId);

        // Build column name -> index map from table schema
        this.columnIndex = buildColumnIndex(table.rowType());

        // Checkpoint directory for stream mode
        this.checkpointPath = Path.of(config.checkpointDir, "stream-scan.checkpoint");

        log.info("Connected to Paimon table: {} ({} columns)", config.tableIdentifier(), columnIndex.size());
    }

    private static Map<String, Integer> buildColumnIndex(RowType rowType) {
        List<DataField> fields = rowType.getFields();
        Map<String, Integer> index = new HashMap<>(fields.size());
        for (int i = 0; i < fields.size(); i++) {
            index.put(fields.get(i).name(), i);
        }
        return index;
    }

    // -- Batch mode -----------------------------------------------------------

    /**
     * Read entire table (latest snapshot), process each row.
     * Returns total rows processed.
     */
    public int readBatch(Consumer<EntityConnection> processor) throws Exception {
        ReadBuilder readBuilder = table.newReadBuilder();
        TableScan scan = readBuilder.newScan();
        TableRead read = readBuilder.newRead();

        List<Split> splits = scan.plan().splits();
        log.info("Batch scan planned: {} splits", splits.size());

        int total = 0;
        for (Split split : splits) {
            try (RecordReader<InternalRow> reader = read.createReader(split)) {
                RecordReader.RecordIterator<InternalRow> batch;
                while ((batch = reader.readBatch()) != null) {
                    InternalRow row;
                    while ((row = batch.next()) != null) {
                        EntityConnection conn = toEntityConnection(row);
                        if (conn != null) {
                            processor.accept(conn);
                            total++;
                        }
                    }
                    batch.releaseBatch();
                }
            }
        }

        log.info("Batch read complete: {} rows", total);
        return total;
    }

    // -- Stream mode ----------------------------------------------------------

    /**
     * Continuously tail the entity_connections changelog.
     * Calls processor for each new/changed row.
     * Blocks until interrupted.
     */
    public void readStream(Consumer<EntityConnection> processor) throws Exception {
        ReadBuilder readBuilder = table.newReadBuilder();
        StreamTableScan scan = readBuilder.newStreamScan();

        // Restore checkpoint if exists
        Long savedState = restoreCheckpoint();
        if (savedState != null) {
            scan.restore(savedState);
            log.info("Restored stream scan from checkpoint: {}", savedState);
        }

        log.info("Starting stream consumer (poll interval: {}ms)", config.pollIntervalMs);

        while (!Thread.currentThread().isInterrupted()) {
            try {
                TableScan.Plan plan = scan.plan();
                List<Split> splits = plan.splits();

                if (splits != null && !splits.isEmpty()) {
                    int processed = 0;
                    TableRead read = readBuilder.newRead();

                    for (Split split : splits) {
                        try (RecordReader<InternalRow> reader = read.createReader(split)) {
                            RecordReader.RecordIterator<InternalRow> batch;
                            while ((batch = reader.readBatch()) != null) {
                                InternalRow row;
                                while ((row = batch.next()) != null) {
                                    EntityConnection conn = toEntityConnection(row);
                                    if (conn != null) {
                                        processor.accept(conn);
                                        processed++;
                                    }
                                }
                                batch.releaseBatch();
                            }
                        }
                    }

                    // Checkpoint after processing
                    Long state = scan.checkpoint();
                    saveCheckpoint(state);

                    if (processed > 0) {
                        log.info("Stream batch: {} rows processed, checkpoint: {}", processed, state);
                    }
                }

                Thread.sleep(config.pollIntervalMs);

            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                log.info("Stream consumer interrupted, shutting down");
                break;
            } catch (org.apache.paimon.table.source.EndOfScanException e) {
                log.info("End of scan reached, sleeping...");
                Thread.sleep(config.pollIntervalMs);
            } catch (Exception e) {
                log.error("Error in stream loop: {}", e.getMessage(), e);
                Thread.sleep(config.pollIntervalMs * 2);  // backoff
            }
        }
    }

    // -- Row conversion -------------------------------------------------------

    /**
     * Convert Paimon InternalRow -> EntityConnection using schema-resolved column indices.
     */
    private EntityConnection toEntityConnection(InternalRow row) {
        try {
            return new EntityConnection(
                row.getLong(col("company_id")),
                row.getLong(col("connection_id")),
                getString(row, col("connection_type")),
                getString(row, col("display_name")),
                getString(row, col("ein")),
                getString(row, col("contact_name")),
                getString(row, col("email")),
                getString(row, col("phone")),
                getString(row, col("category")),
                getString(row, col("commodity")),
                getString(row, col("street_address")),
                getString(row, col("city")),
                getString(row, col("state")),
                getString(row, col("zip")),
                getString(row, col("website")),
                getDecimal(row, col("expected_volume"), 14, 2),
                getString(row, col("payment_terms")),
                getDecimal(row, col("total_volume"), 14, 2),
                getNullableLong(row, col("transaction_count")),
                getDate(row, col("first_transaction")),
                getDate(row, col("last_transaction")),
                getTimestamp(row, col("updated_at"))
            );
        } catch (Exception e) {
            log.warn("Failed to parse row: {}", e.getMessage());
            return null;
        }
    }

    /** Resolve column name to positional index, failing fast on schema mismatch. */
    private int col(String name) {
        Integer idx = columnIndex.get(name);
        if (idx == null) {
            throw new IllegalStateException(
                "Column '" + name + "' not found in table schema. Available: " + columnIndex.keySet());
        }
        return idx;
    }

    private static String getString(InternalRow row, int pos) {
        if (row.isNullAt(pos)) return null;
        BinaryString bs = row.getString(pos);
        return bs != null ? bs.toString() : null;
    }

    private static BigDecimal getDecimal(InternalRow row, int pos, int precision, int scale) {
        if (row.isNullAt(pos)) return null;
        Decimal d = row.getDecimal(pos, precision, scale);
        return d != null ? d.toBigDecimal() : null;
    }

    private static Long getNullableLong(InternalRow row, int pos) {
        if (row.isNullAt(pos)) return null;
        return row.getLong(pos);
    }

    private static LocalDate getDate(InternalRow row, int pos) {
        if (row.isNullAt(pos)) return null;
        // Paimon stores DATE as int (days since epoch)
        int days = row.getInt(pos);
        return LocalDate.ofEpochDay(days);
    }

    private static LocalDateTime getTimestamp(InternalRow row, int pos) {
        if (row.isNullAt(pos)) return null;
        // Paimon TIMESTAMP(3) -> org.apache.paimon.data.Timestamp
        org.apache.paimon.data.Timestamp ts = row.getTimestamp(pos, 3);
        if (ts == null) return null;
        return LocalDateTime.ofInstant(
            Instant.ofEpochMilli(ts.getMillisecond()),
            ZoneId.systemDefault()
        );
    }

    // -- Checkpoint persistence ------------------------------------------------

    /** Delete the checkpoint file so the next stream run starts from the beginning. */
    public void clearCheckpoint() {
        try {
            if (Files.deleteIfExists(checkpointPath)) {
                log.info("Deleted checkpoint: {}", checkpointPath);
            }
        } catch (IOException e) {
            log.warn("Failed to delete checkpoint: {}", e.getMessage());
        }
    }

    private void saveCheckpoint(Long state) {
        if (state == null) return;
        try {
            Files.createDirectories(checkpointPath.getParent());
            Files.writeString(checkpointPath, state.toString());
        } catch (IOException e) {
            log.warn("Failed to save checkpoint: {}", e.getMessage());
        }
    }

    private Long restoreCheckpoint() {
        try {
            if (Files.exists(checkpointPath)) {
                String content = Files.readString(checkpointPath).strip();
                return Long.parseLong(content);
            }
        } catch (Exception e) {
            log.warn("Failed to restore checkpoint: {}", e.getMessage());
        }
        return null;
    }
}
