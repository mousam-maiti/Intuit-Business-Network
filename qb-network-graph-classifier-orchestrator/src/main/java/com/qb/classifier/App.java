package com.qb.classifier;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.qb.classifier.classify.PersonaBuilder;
import com.qb.classifier.client.AgentClient;
import com.qb.classifier.config.Config;
import com.qb.classifier.model.ClassifiedPersona;
import com.qb.classifier.model.EntityConnection;
import com.qb.classifier.model.ResolutionRequest;
import com.qb.classifier.stream.PaimonConsumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * QB Network Graph — Classifier Orchestrator
 *
 * Reads entity_connections from Paimon, classifies each row into a
 * ClassifiedPersona, and POSTs to the Entity Resolution Agent.
 *
 * Usage:
 *   java -jar classifier-orchestrator.jar              # batch mode (default)
 *   java -jar classifier-orchestrator.jar --stream     # stream mode
 *   java -jar classifier-orchestrator.jar --stream --reset  # stream from beginning (clears checkpoint)
 *   java -jar classifier-orchestrator.jar --classify-only   # classify + dump JSON, no agent call
 */
public class App {

    private static final Logger log = LoggerFactory.getLogger(App.class);
    private static final ObjectMapper JSON = new ObjectMapper()
        .enable(SerializationFeature.INDENT_OUTPUT);

    public static void main(String[] args) {
        try {
            Config config = new Config();
            String mode = parseMode(args, config.mode);
            boolean classifyOnly = hasFlag(args, "--classify-only");
            boolean reset = hasFlag(args, "--reset");

            printBanner(config, mode, classifyOnly);

            // Initialize
            PaimonConsumer consumer = new PaimonConsumer(config);

            // Reset checkpoint if requested
            if (reset) {
                consumer.clearCheckpoint();
                log.info("Checkpoint cleared — will process entire table from beginning");
            }
            AgentClient agent = classifyOnly ? null : new AgentClient(
                config.agentBaseUrl, config.agentTimeoutMs, config.dryRun
            );

            // Wire dead-letter sink for failed agent calls
            Path deadLetterDir = Path.of("dead-letter");
            if (agent != null) {
                Files.createDirectories(deadLetterDir);
                agent.setDeadLetterSink(deadLetter -> {
                    try {
                        String filename = String.format("%s-%d.json",
                            deadLetter.request().recordId(), System.currentTimeMillis());
                        Files.writeString(deadLetterDir.resolve(filename),
                            JSON.writeValueAsString(deadLetter));
                    } catch (IOException e) {
                        log.warn("Failed to write dead-letter file: {}", e.getMessage());
                    }
                });
            }

            // Agent health check (unless classify-only or dry-run)
            if (agent != null && !config.dryRun) {
                if (agent.healthCheck()) {
                    log.info("✓ Agent service healthy at {}", config.agentBaseUrl);
                } else {
                    log.warn("⚠ Agent service not reachable at {} — will retry on each request", config.agentBaseUrl);
                }
            }

            // Counters
            AtomicInteger classified = new AtomicInteger(0);
            AtomicInteger skippedNoName = new AtomicInteger(0);

            // Output directory for classify-only mode
            Path outputDir = classifyOnly ? Path.of("classified-output") : null;
            if (outputDir != null) {
                Files.createDirectories(outputDir);
            }

            // Row processor
            java.util.function.Consumer<EntityConnection> processor = conn -> {
                // Skip rows without identity (partial writes from Job 2)
                if (config.skipUnnamed && !conn.hasIdentity()) {
                    skippedNoName.incrementAndGet();
                    return;
                }

                // Classify
                ClassifiedPersona persona = PersonaBuilder.build(conn);
                classified.incrementAndGet();

                if (classifyOnly) {
                    // Dump to JSON file
                    writeClassifiedJson(outputDir, conn, persona);
                } else {
                    // Send to agent
                    ResolutionRequest request = ResolutionRequest.from(conn, persona);
                    String response = agent.resolve(request);

                    if (log.isDebugEnabled() && response != null) {
                        log.debug("[{}] {} → {} | identity={} industry={} location={} commodity={} behavioral={}",
                            conn.connectionType(),
                            conn.displayName(),
                            persona.identity().normalizedName(),
                            persona.sparsity().identity(),
                            persona.sparsity().industry(),
                            persona.sparsity().location(),
                            persona.sparsity().commodity(),
                            persona.sparsity().behavioral()
                        );
                    }
                }

                // Progress logging
                int count = classified.get();
                if (count % 50 == 0) {
                    log.info("Progress: {} classified, {} skipped (no name)", count, skippedNoName.get());
                }
            };

            // Run
            long start = System.currentTimeMillis();

            switch (mode) {
                case "batch" -> {
                    int total = consumer.readBatch(processor);
                    long elapsed = System.currentTimeMillis() - start;
                    printSummary(total, classified.get(), skippedNoName.get(), elapsed, agent, classifyOnly);
                }
                case "stream" -> {
                    // Register shutdown hook
                    Thread mainThread = Thread.currentThread();
                    Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                        log.info("Shutdown signal received...");
                        mainThread.interrupt();
                        try { mainThread.join(5000); } catch (InterruptedException ignored) {}
                        long elapsed = System.currentTimeMillis() - start;
                        printSummary(-1, classified.get(), skippedNoName.get(), elapsed, agent, classifyOnly);
                    }));

                    consumer.readStream(processor);
                }
                default -> {
                    log.error("Unknown mode: {}", mode);
                    System.exit(1);
                }
            }

            if (agent != null) agent.close();

        } catch (Exception e) {
            log.error("Fatal error: {}", e.getMessage(), e);
            System.exit(1);
        }
    }

    // ── CLI parsing ──────────────────────────────────────────

    private static String parseMode(String[] args, String defaultMode) {
        for (String arg : args) {
            if ("--stream".equals(arg)) return "stream";
            if ("--batch".equals(arg)) return "batch";
        }
        return defaultMode;
    }

    private static boolean hasFlag(String[] args, String flag) {
        for (String arg : args) {
            if (flag.equals(arg)) return true;
        }
        return false;
    }

    // ── Output ───────────────────────────────────────────────

    private static void writeClassifiedJson(Path dir, EntityConnection conn, ClassifiedPersona persona) {
        try {
            ResolutionRequest request = ResolutionRequest.from(conn, persona);
            String filename = String.format("%s-%d-%d.json",
                conn.connectionType(), conn.companyId(), conn.connectionId());
            Files.writeString(dir.resolve(filename), JSON.writeValueAsString(request));
        } catch (IOException e) {
            log.warn("Failed to write classified JSON: {}", e.getMessage());
        }
    }

    private static void printBanner(Config config, String mode, boolean classifyOnly) {
        System.out.println();
        System.out.println("  ╔══════════════════════════════════════════════════╗");
        System.out.println("  ║   QB Network Graph — Classifier Orchestrator    ║");
        System.out.println("  ╚══════════════════════════════════════════════════╝");
        System.out.println();
        System.out.printf("  Warehouse:  %s%n", config.warehousePath);
        System.out.printf("  Table:      %s%n", config.tableIdentifier());
        System.out.printf("  Mode:       %s%n", mode);
        if (classifyOnly) {
            System.out.println("  Output:     ./classified-output/ (JSON files)");
        } else {
            System.out.printf("  Agent:      %s%n", config.agentBaseUrl);
        }
        if (config.dryRun) {
            System.out.println("  ⚠  DRY RUN — no agent calls will be made");
        }
        System.out.println();
    }

    private static void printSummary(int totalRows, int classified, int skipped,
                                      long elapsedMs, AgentClient agent, boolean classifyOnly) {
        System.out.println();
        System.out.println("  ────────────────────────────────────────────────");
        System.out.println("  Summary");
        System.out.println("  ────────────────────────────────────────────────");
        if (totalRows >= 0) {
            System.out.printf("  Total rows read:      %d%n", totalRows);
        }
        System.out.printf("  Classified:           %d%n", classified);
        System.out.printf("  Skipped (no name):    %d%n", skipped);
        System.out.printf("  Elapsed:              %.1f s%n", elapsedMs / 1000.0);
        if (classified > 0) {
            System.out.printf("  Avg per record:       %.1f ms%n", (double) elapsedMs / classified);
        }
        if (agent != null) {
            System.out.printf("  Agent:                %s%n", agent.stats());
        }
        if (classifyOnly) {
            System.out.println("  Output:               ./classified-output/");
        }
        if (agent != null && agent.getFailed() > 0) {
            System.out.println("  Dead letters:         ./dead-letter/");
        }
        System.out.println();
    }
}
