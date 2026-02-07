package dev.hjjang.moneyhistory.monitor;

import dev.hjjang.moneyhistory.MoneyHistoryPlugin;
import dev.hjjang.moneyhistory.model.Source;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class AttributionResolver {
    private final MoneyHistoryPlugin plugin;
    private final ConcurrentHashMap<UUID, PlayerContext> playerContexts;

    public AttributionResolver(MoneyHistoryPlugin plugin) {
        this.plugin = plugin;
        this.playerContexts = new ConcurrentHashMap<>();
    }

    public PlayerContext getOrCreateContext(UUID uuid) {
        return playerContexts.computeIfAbsent(uuid,
            k -> new PlayerContext(plugin.getConfigManager().getCommandMemorySeconds()));
    }

    public void removeContext(UUID uuid) {
        playerContexts.remove(uuid);
    }

    public Source resolveSource(UUID playerUuid, double delta, double balanceBefore, double balanceAfter) {
        PlayerContext context = playerContexts.get(playerUuid);
        if (context == null) {
            return analyzePatterns(delta, balanceBefore, balanceAfter);
        }

        // Check for auction commands (within 30 seconds)
        if (context.hasRecentCommand("/auction", 30000)) {
            return Source.PLAYER_AUCTION;
        }

        // Check for pay commands (within 5 seconds)
        if (context.hasRecentCommand("/pay", 5000)) {
            if (delta < 0) {
                return Source.ESSENTIALS_PAY;
            } else {
                return Source.ESSENTIALS_RECEIVE;
            }
        }

        // Check for buy commands (within 5 seconds)
        if (context.hasRecentCommand("/buy", 5000)) {
            return Source.SERVER_SHOP;
        }

        // Check for sell commands (within 15 seconds)
        if (context.hasRecentCommand("/sell", 15000)) {
            return Source.ESSENTIALS_SELL;
        }

        // Check for eco commands (within 10 seconds)
        if (context.hasRecentCommand("/eco", 10000) || context.hasRecentCommand("/economy", 10000)) {
            return Source.ADMIN_COMMAND;
        }

        // Fall back to pattern analysis
        return analyzePatterns(delta, balanceBefore, balanceAfter);
    }

    private Source analyzePatterns(double delta, double balanceBefore, double balanceAfter) {
        double absDelta = Math.abs(delta);
        double roundThreshold = plugin.getConfigManager().getRoundNumberThreshold();
        double roundMultiple = plugin.getConfigManager().getRoundNumberMultiple();

        // Check for round number patterns (likely admin commands)
        if (absDelta >= roundThreshold) {
            if (absDelta % roundMultiple == 0) {
                return Source.LIKELY_ADMIN_COMMAND;
            }
        }

        return Source.UNKNOWN;
    }

    public void clearContext(UUID uuid) {
        playerContexts.remove(uuid);
    }

    public void clearAllContexts() {
        playerContexts.clear();
    }
}
