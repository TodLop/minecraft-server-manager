package dev.hjjang.moneyhistory;

import dev.hjjang.moneyhistory.command.MoneyHistoryCommand;
import dev.hjjang.moneyhistory.config.ConfigManager;
import dev.hjjang.moneyhistory.database.DatabaseManager;
import dev.hjjang.moneyhistory.database.HistoryRecorder;
import dev.hjjang.moneyhistory.database.NameCacheService;
import dev.hjjang.moneyhistory.monitor.AttributionResolver;
import dev.hjjang.moneyhistory.monitor.BalanceMonitor;
import dev.hjjang.moneyhistory.monitor.PlayerContextListener;
import dev.hjjang.moneyhistory.query.HistoryQueryService;
import dev.hjjang.moneyhistory.vault.VaultIntegration;
import org.bukkit.plugin.java.JavaPlugin;

public class MoneyHistoryPlugin extends JavaPlugin {
    private ConfigManager configManager;
    private DatabaseManager databaseManager;
    private VaultIntegration vaultIntegration;
    private HistoryRecorder historyRecorder;
    private NameCacheService nameCacheService;
    private AttributionResolver attributionResolver;
    private BalanceMonitor balanceMonitor;
    private HistoryQueryService queryService;

    @Override
    public void onEnable() {
        try {
            // Phase 1: Configuration
            saveDefaultConfig();
            configManager = new ConfigManager(this);
            getLogger().info("Configuration loaded");

            // Phase 2: Database layer
            databaseManager = new DatabaseManager(this);
            databaseManager.initialize();
            getLogger().info("Database initialized");

            // Phase 2: Name cache service
            nameCacheService = new NameCacheService(this, databaseManager);
            getServer().getPluginManager().registerEvents(nameCacheService, this);
            getLogger().info("Name cache service initialized");

            // Phase 2: History recorder
            historyRecorder = new HistoryRecorder(this, databaseManager);
            historyRecorder.start();
            getLogger().info("History recorder started");

            // Phase 3: Vault integration
            vaultIntegration = new VaultIntegration(this);
            if (!vaultIntegration.setupEconomy()) {
                getLogger().severe("Failed to hook into Vault economy! Disabling plugin.");
                getServer().getPluginManager().disablePlugin(this);
                return;
            }
            getLogger().info("Hooked into " + vaultIntegration.getEconomyName() + " economy");

            // Phase 3: Attribution resolver
            attributionResolver = new AttributionResolver(this);
            getLogger().info("Attribution resolver initialized");

            // Phase 3: Player context listener
            PlayerContextListener contextListener = new PlayerContextListener(attributionResolver);
            getServer().getPluginManager().registerEvents(contextListener, this);
            getLogger().info("Player context listener registered");

            // Phase 3: Balance monitor
            balanceMonitor = new BalanceMonitor(this, vaultIntegration, attributionResolver, historyRecorder, nameCacheService);
            balanceMonitor.start();
            getLogger().info("Balance monitor started (" + configManager.getMonitoringPollInterval() + "s interval)");

            // Phase 4: Query service
            queryService = new HistoryQueryService(this, databaseManager, nameCacheService);
            getLogger().info("Query service initialized");

            // Phase 5: Commands
            MoneyHistoryCommand commandHandler = new MoneyHistoryCommand(this, queryService, configManager, databaseManager);
            getCommand("moneyhistory").setExecutor(commandHandler);
            getCommand("moneyhistory").setTabCompleter(commandHandler);
            getLogger().info("Commands registered");

            getLogger().info("MoneyHistory v" + getDescription().getVersion() + " enabled!");

        } catch (Exception e) {
            getLogger().severe("Failed to enable MoneyHistory: " + e.getMessage());
            getLogger().log(java.util.logging.Level.SEVERE, "Stack trace:", e);
            getServer().getPluginManager().disablePlugin(this);
        }
    }

    @Override
    public void onDisable() {
        // Stop balance monitor
        if (balanceMonitor != null) {
            balanceMonitor.stop();
            getLogger().info("Balance monitor stopped");
        }

        // Flush and stop history recorder
        if (historyRecorder != null) {
            historyRecorder.stop();
            getLogger().info("History recorder stopped and flushed");
        }

        // Close database
        if (databaseManager != null) {
            databaseManager.close();
            getLogger().info("Database closed");
        }

        getLogger().info("MoneyHistory disabled");
    }

    // Getters for components
    public ConfigManager getConfigManager() {
        return configManager;
    }

    public DatabaseManager getDatabaseManager() {
        return databaseManager;
    }

    public VaultIntegration getVaultIntegration() {
        return vaultIntegration;
    }

    public HistoryRecorder getHistoryRecorder() {
        return historyRecorder;
    }

    public NameCacheService getNameCacheService() {
        return nameCacheService;
    }

    public AttributionResolver getAttributionResolver() {
        return attributionResolver;
    }

    public BalanceMonitor getBalanceMonitor() {
        return balanceMonitor;
    }

    public HistoryQueryService getQueryService() {
        return queryService;
    }
}
