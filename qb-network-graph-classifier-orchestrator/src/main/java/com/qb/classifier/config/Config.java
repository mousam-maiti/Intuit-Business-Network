package com.qb.classifier.config;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

/**
 * Configuration loaded from app.properties on the classpath, with env var overrides.
 */
public class Config {

    public final String warehousePath;
    public final String database;
    public final String sourceTable;

    public final String agentBaseUrl;
    public final int agentTimeoutMs;

    public final String mode;           // "batch" or "stream"
    public final long pollIntervalMs;
    public final String checkpointDir;

    public final boolean skipUnnamed;
    public final boolean dryRun;
    public final String logLevel;

    public Config() {
        Properties props = loadProperties();

        this.warehousePath  = get(props, "warehouse.path", "/tmp/paimon-warehouse");
        this.database       = get(props, "paimon.database", "network_graph");
        this.sourceTable    = get(props, "source.table", "entity_connections");

        this.agentBaseUrl   = get(props, "agent.base-url", "http://localhost:8000");
        this.agentTimeoutMs = getInt(props, "agent.timeout-ms", 10_000);

        this.mode           = get(props, "mode", "batch");
        this.pollIntervalMs = getLong(props, "poll.interval-ms", 2000);
        this.checkpointDir  = get(props, "checkpoint.dir", ".checkpoints");

        this.skipUnnamed    = getBool(props, "skip.unnamed", true);
        this.dryRun         = getBool(props, "dry.run", false);
        this.logLevel       = get(props, "log.level", "INFO");
    }

    public String tableIdentifier() {
        return database + "." + sourceTable;
    }

    private static Properties loadProperties() {
        Properties props = new Properties();
        try (InputStream in = Config.class.getClassLoader().getResourceAsStream("app.properties")) {
            if (in != null) {
                props.load(in);
            }
        } catch (IOException e) {
            // Fall through to defaults
        }
        return props;
    }

    /** Property lookup with env var override. Env var key = uppercased, dots → underscores. */
    private static String get(Properties props, String key, String def) {
        String envKey = key.replace('.', '_').replace('-', '_').toUpperCase();
        String env = System.getenv(envKey);
        if (env != null) return env;
        return props.getProperty(key, def);
    }

    private static int getInt(Properties props, String key, int def) {
        try { return Integer.parseInt(get(props, key, String.valueOf(def))); }
        catch (NumberFormatException e) { return def; }
    }

    private static long getLong(Properties props, String key, long def) {
        try { return Long.parseLong(get(props, key, String.valueOf(def))); }
        catch (NumberFormatException e) { return def; }
    }

    private static boolean getBool(Properties props, String key, boolean def) {
        return Boolean.parseBoolean(get(props, key, String.valueOf(def)));
    }

    @Override
    public String toString() {
        return String.format(
            "Config{warehouse=%s, table=%s.%s, agent=%s, mode=%s, dryRun=%s}",
            warehousePath, database, sourceTable, agentBaseUrl, mode, dryRun);
    }
}
