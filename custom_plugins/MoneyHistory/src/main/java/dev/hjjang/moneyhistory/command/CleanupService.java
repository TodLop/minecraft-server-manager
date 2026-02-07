package dev.hjjang.moneyhistory.command;

import dev.hjjang.moneyhistory.MoneyHistoryPlugin;
import dev.hjjang.moneyhistory.database.DatabaseManager;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class CleanupService {
    private final MoneyHistoryPlugin plugin;
    private final DatabaseManager databaseManager;

    public CleanupService(MoneyHistoryPlugin plugin, DatabaseManager databaseManager) {
        this.plugin = plugin;
        this.databaseManager = databaseManager;
    }

    public CompletableFuture<Integer> cleanup(int days) {
        return CompletableFuture.supplyAsync(() -> {
            long cutoffMs = System.currentTimeMillis() - TimeUnit.DAYS.toMillis(days);
            int deletedCount = 0;

            try {
                // Delete old records in batches
                deletedCount = deleteOldRecords(cutoffMs);

                // VACUUM to reclaim space
                vacuum();

                plugin.getLogger().info("Cleanup completed: deleted " + deletedCount + " records older than " + days + " days");

                return deletedCount;

            } catch (SQLException e) {
                plugin.getLogger().severe("Cleanup failed: " + e.getMessage());
                plugin.getLogger().log(java.util.logging.Level.SEVERE, "Stack trace:", e);
                throw new RuntimeException(e);
            }
        });
    }

    private int deleteOldRecords(long cutoffMs) throws SQLException {
        int totalDeleted = 0;
        int batchSize = 1000;

        try (Connection conn = databaseManager.getConnection()) {
            conn.setAutoCommit(false);

            try {
                String deleteSql = "DELETE FROM balance_history WHERE timestamp_ms < ? LIMIT ?";

                while (true) {
                    try (PreparedStatement stmt = conn.prepareStatement(deleteSql)) {
                        stmt.setLong(1, cutoffMs);
                        stmt.setInt(2, batchSize);

                        int deleted = stmt.executeUpdate();
                        totalDeleted += deleted;

                        if (deleted < batchSize) {
                            // No more records to delete
                            break;
                        }

                        conn.commit();
                    }
                }

                conn.commit();

            } catch (SQLException e) {
                conn.rollback();
                throw e;
            } finally {
                conn.setAutoCommit(true);
            }
        }

        return totalDeleted;
    }

    private void vacuum() throws SQLException {
        plugin.getLogger().info("Running VACUUM to reclaim database space...");

        try (Connection conn = databaseManager.getConnection();
             Statement stmt = conn.createStatement()) {
            stmt.execute("VACUUM");
        }

        plugin.getLogger().info("VACUUM completed");
    }
}
