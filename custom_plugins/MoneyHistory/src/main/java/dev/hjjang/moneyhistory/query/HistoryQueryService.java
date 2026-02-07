package dev.hjjang.moneyhistory.query;

import dev.hjjang.moneyhistory.MoneyHistoryPlugin;
import dev.hjjang.moneyhistory.database.DatabaseManager;
import dev.hjjang.moneyhistory.database.NameCacheService;
import dev.hjjang.moneyhistory.model.HistoryEntry;
import dev.hjjang.moneyhistory.model.Source;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;

public class HistoryQueryService {
    private final MoneyHistoryPlugin plugin;
    private final DatabaseManager databaseManager;
    private final NameCacheService nameCacheService;
    private final ConcurrentHashMap<String, CachedCount> countCache;

    private static final long COUNT_CACHE_DURATION_MS = 60000; // 60 seconds

    public HistoryQueryService(MoneyHistoryPlugin plugin, DatabaseManager databaseManager,
                              NameCacheService nameCacheService) {
        this.plugin = plugin;
        this.databaseManager = databaseManager;
        this.nameCacheService = nameCacheService;
        this.countCache = new ConcurrentHashMap<>();
    }

    public CompletableFuture<List<HistoryEntry>> getHistory(UUID playerUuid, int page, HistoryFilters filters) {
        return CompletableFuture.supplyAsync(() -> {
            long startTime = System.currentTimeMillis();

            try {
                int entriesPerPage = plugin.getConfigManager().getEntriesPerPage();
                List<HistoryEntry> entries = queryHistory(playerUuid, page, filters, entriesPerPage);

                long elapsed = System.currentTimeMillis() - startTime;
                if (plugin.getConfigManager().isLogSlowOperations() &&
                    elapsed > plugin.getConfigManager().getSlowThresholdMs()) {
                    plugin.getLogger().warning(
                        String.format("Slow history query: %dms for player %s (page %d, %d entries)",
                            elapsed, playerUuid, page, entries.size())
                    );
                }

                return entries;

            } catch (SQLException e) {
                plugin.getLogger().severe("Failed to query history: " + e.getMessage());
                plugin.getLogger().log(java.util.logging.Level.SEVERE, "Stack trace:", e);
                return new ArrayList<>();
            }
        });
    }

    public CompletableFuture<Integer> getHistoryCount(UUID playerUuid, HistoryFilters filters) {
        return CompletableFuture.supplyAsync(() -> {
            // Check cache first
            String cacheKey = playerUuid.toString() + "_" + (filters != null ? filters.hashCode() : 0);
            CachedCount cached = countCache.get(cacheKey);
            if (cached != null && !cached.isExpired()) {
                return cached.count;
            }

            try {
                int count = queryCount(playerUuid, filters);

                // Update cache
                countCache.put(cacheKey, new CachedCount(count, System.currentTimeMillis()));

                return count;

            } catch (SQLException e) {
                plugin.getLogger().severe("Failed to query history count: " + e.getMessage());
                plugin.getLogger().log(java.util.logging.Level.SEVERE, "Stack trace:", e);
                return 0;
            }
        });
    }

    private List<HistoryEntry> queryHistory(UUID playerUuid, int page, HistoryFilters filters, int entriesPerPage)
            throws SQLException {
        List<HistoryEntry> entries = new ArrayList<>();

        QueryBuilder builder = QueryBuilder.buildHistoryQuery(playerUuid, filters, page, entriesPerPage);

        try (Connection conn = databaseManager.getConnection();
             PreparedStatement stmt = builder.prepareStatement(conn);
             ResultSet rs = stmt.executeQuery()) {

            while (rs.next()) {
                entries.add(parseHistoryEntry(rs));
            }
        }

        return entries;
    }

    private int queryCount(UUID playerUuid, HistoryFilters filters) throws SQLException {
        QueryBuilder builder = QueryBuilder.buildCountQuery(playerUuid, filters);

        try (Connection conn = databaseManager.getConnection();
             PreparedStatement stmt = builder.prepareStatement(conn);
             ResultSet rs = stmt.executeQuery()) {

            if (rs.next()) {
                return rs.getInt(1);
            }
        }

        return 0;
    }

    private HistoryEntry parseHistoryEntry(ResultSet rs) throws SQLException {
        long id = rs.getLong("id");
        UUID playerUuid = UUID.fromString(rs.getString("player_uuid"));
        String playerName = rs.getString("player_name");
        long timestampMs = rs.getLong("timestamp_ms");
        double balanceBefore = rs.getDouble("balance_before");
        double balanceAfter = rs.getDouble("balance_after");
        double delta = rs.getDouble("delta");
        Source source = Source.valueOf(rs.getString("source"));
        String details = rs.getString("details");

        return new HistoryEntry(id, playerUuid, playerName, timestampMs,
                               balanceBefore, balanceAfter, delta, source, details);
    }

    public void clearCache() {
        countCache.clear();
    }

    private static class CachedCount {
        final int count;
        final long timestamp;

        CachedCount(int count, long timestamp) {
            this.count = count;
            this.timestamp = timestamp;
        }

        boolean isExpired() {
            return System.currentTimeMillis() - timestamp > COUNT_CACHE_DURATION_MS;
        }
    }
}
