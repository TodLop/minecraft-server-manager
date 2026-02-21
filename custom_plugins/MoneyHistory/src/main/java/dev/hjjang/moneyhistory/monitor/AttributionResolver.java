package dev.hjjang.moneyhistory.monitor;

import dev.hjjang.moneyhistory.MoneyHistoryPlugin;
import dev.hjjang.moneyhistory.model.AttributionResult;
import dev.hjjang.moneyhistory.model.Source;

import java.util.List;
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

    public AttributionResult resolveSource(UUID playerUuid, double delta, double balanceBefore, double balanceAfter) {
        PlayerContext context = playerContexts.get(playerUuid);
        if (context == null) {
            return analyzePatterns(delta, balanceBefore, balanceAfter);
        }

        // Check for auction commands (within 30 seconds)
        if (context.hasRecentCommand("/auction", 30000)) {
            String lastAuctionCmd = getLastCommandMatching(context, "/auction");
            return new AttributionResult(Source.PLAYER_AUCTION, lastAuctionCmd);
        }

        // Check for pay commands (within 5 seconds)
        if (context.hasRecentCommand("/pay", 5000)) {
            if (delta < 0) {
                return new AttributionResult(Source.ESSENTIALS_PAY, getLastCommandMatching(context, "/pay"));
            } else {
                return new AttributionResult(Source.ESSENTIALS_RECEIVE, "Received payment");
            }
        }

        // Ultra Cosmetics: /uc opens GUI, purchase happens via click (~10s window)
        if (context.hasRecentCommand("/uc", 10000) || context.hasRecentCommand("/ultracosmetics", 10000)) {
            if (delta < 0) {
                return new AttributionResult(Source.ULTRA_COSMETICS, "Key purchase");
            }
        }

        // Check for buy commands (within 5 seconds)
        if (context.hasRecentCommand("/buy", 5000)) {
            return new AttributionResult(Source.SERVER_SHOP, "ServerShop purchase");
        }

        // Check for sell commands (within 15 seconds)
        if (context.hasRecentCommand("/sell", 15000)) {
            return new AttributionResult(Source.ESSENTIALS_SELL, getLastCommandMatching(context, "/sell"));
        }

        // Check for eco commands (within 10 seconds)
        if (context.hasRecentCommand("/eco", 10000) || context.hasRecentCommand("/economy", 10000)) {
            return new AttributionResult(Source.ADMIN_COMMAND, "Admin economy command");
        }

        // Fall back to pattern analysis
        return analyzePatterns(delta, balanceBefore, balanceAfter);
    }

    private AttributionResult analyzePatterns(double delta, double balanceBefore, double balanceAfter) {
        double absDelta = Math.abs(delta);
        double roundThreshold = plugin.getConfigManager().getRoundNumberThreshold();
        double roundMultiple = plugin.getConfigManager().getRoundNumberMultiple();

        // Check for round number patterns (likely admin commands)
        if (absDelta >= roundThreshold) {
            if (absDelta % roundMultiple == 0) {
                return new AttributionResult(Source.LIKELY_ADMIN_COMMAND, "Round number pattern detected");
            }
        }

        return new AttributionResult(Source.UNKNOWN);
    }

    private String getLastCommandMatching(PlayerContext context, String prefix) {
        List<PlayerContext.CommandRecord> commands = context.getRecentCommands();
        String lastMatch = null;
        for (PlayerContext.CommandRecord record : commands) {
            if (record.command.toLowerCase().startsWith(prefix.toLowerCase())) {
                lastMatch = record.command;
            }
        }
        return lastMatch;
    }

    public void clearContext(UUID uuid) {
        playerContexts.remove(uuid);
    }

    public void clearAllContexts() {
        playerContexts.clear();
    }
}
