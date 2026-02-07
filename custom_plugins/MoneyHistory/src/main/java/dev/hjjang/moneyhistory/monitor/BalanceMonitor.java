package dev.hjjang.moneyhistory.monitor;

import dev.hjjang.moneyhistory.MoneyHistoryPlugin;
import dev.hjjang.moneyhistory.database.HistoryRecorder;
import dev.hjjang.moneyhistory.database.NameCacheService;
import dev.hjjang.moneyhistory.model.BalanceChange;
import dev.hjjang.moneyhistory.model.Source;
import dev.hjjang.moneyhistory.vault.VaultIntegration;
import net.milkbowl.vault.economy.Economy;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.scheduler.BukkitTask;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class BalanceMonitor implements Listener {
    private final MoneyHistoryPlugin plugin;
    private final VaultIntegration vaultIntegration;
    private final AttributionResolver attributionResolver;
    private final HistoryRecorder historyRecorder;
    private final NameCacheService nameCacheService;
    private final ConcurrentHashMap<UUID, Double> balanceCache;
    private BukkitTask monitorTask;
    private volatile boolean running;

    public BalanceMonitor(MoneyHistoryPlugin plugin, VaultIntegration vaultIntegration,
                         AttributionResolver attributionResolver, HistoryRecorder historyRecorder,
                         NameCacheService nameCacheService) {
        this.plugin = plugin;
        this.vaultIntegration = vaultIntegration;
        this.attributionResolver = attributionResolver;
        this.historyRecorder = historyRecorder;
        this.nameCacheService = nameCacheService;
        this.balanceCache = new ConcurrentHashMap<>();
        this.running = false;
    }

    public void start() {
        if (running) {
            return;
        }

        running = true;

        // Register offline detection listener if enabled
        if (plugin.getConfigManager().isOfflineDetectionEnabled()) {
            plugin.getServer().getPluginManager().registerEvents(this, plugin);
        }

        // Initialize balance cache for online players
        for (Player player : plugin.getServer().getOnlinePlayers()) {
            Economy economy = vaultIntegration.getEconomy();
            double balance = economy.getBalance(player);
            balanceCache.put(player.getUniqueId(), balance);
            nameCacheService.updateLastBalance(player.getUniqueId(), balance);
        }

        // Start periodic polling
        int intervalSeconds = plugin.getConfigManager().getMonitoringPollInterval();
        int intervalTicks = intervalSeconds * 20;

        monitorTask = plugin.getServer().getScheduler().runTaskTimerAsynchronously(
            plugin,
            this::pollBalances,
            intervalTicks,
            intervalTicks
        );

        plugin.getLogger().info("Balance monitor started with " + intervalSeconds + "s polling interval");
    }

    public void stop() {
        running = false;

        if (monitorTask != null) {
            monitorTask.cancel();
            monitorTask = null;
        }

        balanceCache.clear();
    }

    private void pollBalances() {
        if (!running) {
            return;
        }

        long startTime = System.currentTimeMillis();
        Economy economy = vaultIntegration.getEconomy();
        int changesDetected = 0;

        for (Player player : plugin.getServer().getOnlinePlayers()) {
            UUID uuid = player.getUniqueId();
            double currentBalance = economy.getBalance(player);
            Double cachedBalance = balanceCache.get(uuid);

            if (cachedBalance == null) {
                // First time seeing this player, just cache the balance
                balanceCache.put(uuid, currentBalance);
                nameCacheService.updateLastBalance(uuid, currentBalance);
                continue;
            }

            double delta = currentBalance - cachedBalance;
            double threshold = plugin.getConfigManager().getUnknownThreshold();

            // Check if balance changed significantly
            if (Math.abs(delta) > threshold) {
                // Balance changed, record it
                Source source = attributionResolver.resolveSource(uuid, delta, cachedBalance, currentBalance);

                BalanceChange change = new BalanceChange(
                    uuid,
                    player.getName(),
                    System.currentTimeMillis(),
                    cachedBalance,
                    currentBalance,
                    source,
                    null
                );

                historyRecorder.record(change);
                changesDetected++;

                // Update cache
                balanceCache.put(uuid, currentBalance);
                nameCacheService.updateLastBalance(uuid, currentBalance);

                // Log large unexplained changes
                if (Math.abs(delta) > 10000 && source == Source.UNKNOWN) {
                    plugin.getLogger().warning(
                        String.format("Large unknown balance change for %s: %.2f (balance: %.2f -> %.2f)",
                            player.getName(), delta, cachedBalance, currentBalance)
                    );
                }
            }
        }

        long elapsed = System.currentTimeMillis() - startTime;
        if (plugin.getConfigManager().isLogSlowOperations() &&
            elapsed > plugin.getConfigManager().getSlowThresholdMs()) {
            plugin.getLogger().warning(
                String.format("Slow balance poll: %dms for %d players (%d changes)",
                    elapsed, plugin.getServer().getOnlinePlayers().size(), changesDetected)
            );
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPlayerJoin(PlayerJoinEvent event) {
        if (!plugin.getConfigManager().isOfflineDetectionEnabled()) {
            return;
        }

        Player player = event.getPlayer();
        UUID uuid = player.getUniqueId();
        Economy economy = vaultIntegration.getEconomy();
        double currentBalance = economy.getBalance(player);

        // Check for offline balance changes
        Double lastBalance = nameCacheService.getLastBalance(uuid);
        if (lastBalance != null) {
            double delta = currentBalance - lastBalance;
            double threshold = plugin.getConfigManager().getUnknownThreshold();

            if (Math.abs(delta) > threshold) {
                // Balance changed while offline
                BalanceChange change = new BalanceChange(
                    uuid,
                    player.getName(),
                    System.currentTimeMillis(),
                    lastBalance,
                    currentBalance,
                    Source.OFFLINE_CHANGE,
                    "Balance changed while offline"
                );

                historyRecorder.record(change);

                plugin.getLogger().info(
                    String.format("Offline balance change detected for %s: %.2f (%.2f -> %.2f)",
                        player.getName(), delta, lastBalance, currentBalance)
                );
            }
        }

        // Update cache
        balanceCache.put(uuid, currentBalance);
        nameCacheService.updateLastBalance(uuid, currentBalance);
    }

    public boolean isRunning() {
        return running;
    }

    public int getCachedPlayerCount() {
        return balanceCache.size();
    }
}
