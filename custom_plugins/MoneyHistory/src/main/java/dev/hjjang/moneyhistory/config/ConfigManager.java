package dev.hjjang.moneyhistory.config;

import dev.hjjang.moneyhistory.MoneyHistoryPlugin;
import org.bukkit.configuration.file.FileConfiguration;

public class ConfigManager {
    private final MoneyHistoryPlugin plugin;
    private FileConfiguration config;

    public ConfigManager(MoneyHistoryPlugin plugin) {
        this.plugin = plugin;
        reload();
    }

    public void reload() {
        plugin.reloadConfig();
        this.config = plugin.getConfig();
    }

    // Monitoring settings
    public int getMonitoringPollInterval() {
        return config.getInt("monitoring.poll-interval-seconds", 10);
    }

    public boolean isOfflineDetectionEnabled() {
        return config.getBoolean("monitoring.enable-offline-detection", true);
    }

    public double getUnknownThreshold() {
        return config.getDouble("monitoring.unknown-threshold", 0.01);
    }

    // Attribution settings
    public int getCommandMemorySeconds() {
        return config.getInt("attribution.command-memory-seconds", 30);
    }

    public double getRoundNumberThreshold() {
        return config.getDouble("attribution.admin-command-patterns.round-number-threshold", 1000.0);
    }

    public double getRoundNumberMultiple() {
        return config.getDouble("attribution.admin-command-patterns.round-number-multiple", 100.0);
    }

    // Database settings
    public int getBatchSize() {
        return config.getInt("database.batch-size", 100);
    }

    public int getBatchDelaySeconds() {
        return config.getInt("database.batch-delay-seconds", 2);
    }

    public boolean isDailyBackupEnabled() {
        return config.getBoolean("database.enable-daily-backup", true);
    }

    // Display settings
    public int getEntriesPerPage() {
        return config.getInt("display.entries-per-page", 10);
    }

    public int getMaxPages() {
        return config.getInt("display.max-pages", 100);
    }

    public boolean isShowUnknownHelp() {
        return config.getBoolean("display.show-unknown-help", true);
    }

    public boolean isUseRelativeTime() {
        return config.getBoolean("display.use-relative-time", true);
    }

    // Maintenance settings
    public boolean isAutoCleanupEnabled() {
        return config.getBoolean("maintenance.enable-auto-cleanup", false);
    }

    public boolean isLogSlowOperations() {
        return config.getBoolean("maintenance.log-slow-operations", true);
    }

    public int getSlowThresholdMs() {
        return config.getInt("maintenance.slow-threshold-ms", 50);
    }
}
