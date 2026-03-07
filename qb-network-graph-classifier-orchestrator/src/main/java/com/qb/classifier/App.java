package com.qb.classifier;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.qb.classifier.classifier.PersonaBuilder;
import com.qb.classifier.classifier.impl.*;
import com.qb.classifier.client.ResolutionClient;
import com.qb.classifier.client.SyncClient;
import com.qb.classifier.client.impl.HttpResolutionClient;
import com.qb.classifier.client.impl.HttpSyncClient;
import com.qb.classifier.config.Config;
import com.qb.classifier.model.ClassifiedPersona;
import com.qb.classifier.model.EntityConnection;
import com.qb.classifier.model.ResolutionRequest;
import com.qb.classifier.service.ClassificationService;
import com.qb.classifier.stream.EntityConnectionSource;
import com.qb.classifier.stream.ResolvedEntitySink;
import com.qb.classifier.stream.impl.PaimonSink;
import com.qb.classifier.stream.impl.PaimonSource;
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
 *   java -jar classifier-orchestrator.jar              # batch two-pass (default)
 *   java -jar classifier-orchestrator.jar --stream     # stream two-pass (fast → full per record)
 *   java -jar classifier-orchestrator.jar --stream --reset  # stream from beginning
 *   java -jar classifier-orchestrator.jar --classify-only   # classify + dump JSON, no agent call
 *   java -jar classifier-orchestrator.jar --batch --fast    # batch pass-1 only: deterministic, parks ambiguous
 *   java -jar classifier-orchestrator.jar --batch           # batch two-pass (fast → full fallback per record)
 *
 * Two-pass resolution (default for both batch and stream):
 *   Pass 1: fast deterministic only (~35ms/record, resolves ~70%)
 *   Pass 2: if REVIEW → full resolution with embedding + LLM for ambiguous
 *   --fast disables pass 2 (batch-only workflow for corpus enrichment)
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
            boolean fastMode = hasFlag(args, "--fast");

            printBanner(config, mode, classifyOnly, fastMode);

            // ── Wire dependencies ─────────────────────────────
            PersonaBuilder personaBuilder = new PersonaBuilder(
                new NameClassifier(),
                new IdentityClassifier(),
                new IndustryClassifier(),
                new LocationClassifier(),
                new CommodityClassifier(),
                new BehavioralClassifier()
            );

            EntityConnectionSource source = new PaimonSource(config);

            HttpResolutionClient httpClient = classifyOnly ? null : new HttpResolutionClient(
                config.agentBaseUrl, config.agentTimeoutMs, config.dryRun
            );
            ResolutionClient agent = httpClient;

            ResolvedEntitySink sink = classifyOnly ? null : new PaimonSink(config);

            SyncClient syncClient = classifyOnly ? null : new HttpSyncClient(config.syncBaseUrl);

            ClassificationService classificationService = new ClassificationService(
                personaBuilder, agent, sink, syncClient
            );
            classificationService.setFastMode(fastMode);
            // --fast disables two-pass (pass-1-only for batch workflow)
            // Without --fast, two-pass is automatic (fast first → full if REVIEW)
            if (fastMode) {
                classificationService.setTwoPass(false);
            }

            // Reset checkpoint if requested
            if (reset) {
                source.clearCheckpoint();
                log.info("Checkpoint cleared — will process entire table from beginning");
            }

            // Wire dead-letter sink for failed agent calls
            if (httpClient != null) {
                Path deadLetterDir = Path.of("dead-letter");
                Files.createDirectories(deadLetterDir);
                httpClient.setDeadLetterSink(deadLetter -> {
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
                if (config.skipUnnamed && !conn.hasIdentity()) {
                    skippedNoName.incrementAndGet();
                    return;
                }

                if (classifyOnly) {
                    ClassifiedPersona persona = classificationService.classify(conn);
                    classified.incrementAndGet();
                    writeClassifiedJson(outputDir, conn, persona);
                } else {
                    classificationService.classifyAndResolve(conn);
                    classified.incrementAndGet();
                }

                int count = classified.get();
                if (count % 50 == 0) {
                    log.info("Progress: {} classified, {} skipped (no name)", count, skippedNoName.get());
                }
            };

            // Run
            long start = System.currentTimeMillis();

            switch (mode) {
                case "batch" -> {
                    int total = source.readAll(processor);
                    long elapsed = System.currentTimeMillis() - start;
                    printSummary(total, classified.get(), skippedNoName.get(), elapsed,
                        agent, classifyOnly, classificationService);
                }
                case "stream" -> {
                    Thread mainThread = Thread.currentThread();
                    Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                        log.info("Shutdown signal received...");
                        mainThread.interrupt();
                        try { mainThread.join(5000); } catch (InterruptedException ignored) {}
                        long elapsed = System.currentTimeMillis() - start;
                        printSummary(-1, classified.get(), skippedNoName.get(), elapsed,
                            agent, classifyOnly, classificationService);
                    }));

                    source.streamChanges(processor);
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

    private static void printBanner(Config config, String mode, boolean classifyOnly, boolean fastMode) {
        System.out.println();
        System.out.println("  ╔══════════════════════════════════════════════════╗");
        System.out.println("  ║   QB Network Graph — Classifier Orchestrator    ║");
        System.out.println("  ╚══════════════════════════════════════════════════╝");
        System.out.println();
        System.out.printf("  Warehouse:  %s%n", config.warehousePath);
        System.out.printf("  Table:      %s%n", config.tableIdentifier());
        System.out.printf("  Mode:       %s%n", mode);
        if (fastMode) {
            System.out.println("  Fast mode:  ON (pass-1 only: deterministic, parks ambiguous)");
        } else {
            System.out.println("  Two-pass:   ON (fast deterministic → full fallback for ambiguous)");
        }
        if (classifyOnly) {
            System.out.println("  Output:     ./classified-output/ (JSON files)");
        } else {
            System.out.printf("  Agent:      %s%n", config.agentBaseUrl);
        }
        if (config.dryRun) {
            System.out.println("  ⚠  DRY RUN — no agent calls will be made");
        }
        System.out.println();
        System.out.flush();
    }

    private static void printSummary(int totalRows, int classified, int skipped,
                                      long elapsedMs, ResolutionClient agent, boolean classifyOnly,
                                      ClassificationService svc) {
        System.out.println();
        System.out.println("  ────────────────────────────────────────────────");
        System.out.println("  Summary");
        System.out.println("  ────────────────────────────────────────────────");
        if (totalRows >= 0) {
            System.out.printf("  Total rows read:      %d%n", totalRows);
        }
        System.out.printf("  Classified:           %d%n", classified);
        System.out.printf("  Skipped (no name):    %d%n", skipped);
        if (svc != null && (svc.getFastPassResolved() > 0 || svc.getFullPassFallbacks() > 0)) {
            System.out.printf("  Fast-pass resolved:   %d%n", svc.getFastPassResolved());
            System.out.printf("  Full-pass fallbacks:  %d%n", svc.getFullPassFallbacks());
        }
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
        System.out.flush();
    }
}
