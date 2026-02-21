package dev.hjjang.moneyhistory.database;

import dev.hjjang.moneyhistory.MoneyHistoryPlugin;
import dev.hjjang.moneyhistory.model.BalanceChange;
import org.bukkit.scheduler.BukkitTask;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.LinkedBlockingQueue;

public class HistoryRecorder {
    private final MoneyHistoryPlugin plugin;
    private final DatabaseManager databaseManager;
    private final LinkedBlockingQueue<BalanceChange> writeQueue;
    private BukkitTask writeTask;
    private volatile boolean running;

    public HistoryRecorder(MoneyHistoryPlugin plugin, DatabaseManager databaseManager) {
        this.plugin = plugin;
        this.databaseManager = databaseManager;
        this.writeQueue = new LinkedBlockingQueue<>();
        this.running = false;
    }

    public void start() {
        if (running) {
            return;
        }

        running = true;
        int delaySeconds = plugin.getConfigManager().getBatchDelaySeconds();
        int delayTicks = delaySeconds * 20; // Convert seconds to ticks

        // Start async write task
        writeTask = plugin.getServer().getScheduler().runTaskTimerAsynchronously(
            plugin,
            this::processBatch,
            delayTicks,
            delayTicks
        );

        plugin.getLogger().info("History recorder task scheduled (every " + delaySeconds + "s)");
    }

    public void stop() {
        running = false;

        if (writeTask != null) {
            writeTask.cancel();
            writeTask = null;
        }

        // Flush remaining entries
        if (!writeQueue.isEmpty()) {
            plugin.getLogger().info("Flushing " + writeQueue.size() + " pending entries...");
            processBatch();
        }
    }

    public void record(BalanceChange change) {
        if (!running) {
            plugin.getLogger().warning("Attempted to record balance change while recorder is stopped");
            return;
        }

        writeQueue.offer(change);

        // If queue exceeds batch size, trigger immediate write
        int batchSize = plugin.getConfigManager().getBatchSize();
        if (writeQueue.size() >= batchSize) {
            plugin.getServer().getScheduler().runTaskAsynchronously(plugin, this::processBatch);
        }
    }

    private void processBatch() {
        if (writeQueue.isEmpty()) {
            return;
        }

        long startTime = System.currentTimeMillis();
        List<BalanceChange> batch = new ArrayList<>();
        writeQueue.drainTo(batch);

        if (batch.isEmpty()) {
            return;
        }

        try {
            writeBatch(batch);

            long elapsed = System.currentTimeMillis() - startTime;
            if (plugin.getConfigManager().isLogSlowOperations() &&
                elapsed > plugin.getConfigManager().getSlowThresholdMs()) {
                plugin.getLogger().warning(
                    String.format("Slow batch write: %d entries in %dms", batch.size(), elapsed)
                );
            }

        } catch (SQLException e) {
            plugin.getLogger().severe("Failed to write batch of " + batch.size() + " entries: " + e.getMessage());
            plugin.getLogger().log(java.util.logging.Level.SEVERE, "Stack trace:", e);

            // Re-queue failed entries for retry
            writeQueue.addAll(batch);
        }
    }

    private void writeBatch(List<BalanceChange> changes) throws SQLException {
        databaseManager.executeBatch(conn -> {
            String sql = "INSERT INTO balance_history " +
                        "(player_uuid, player_name, timestamp_ms, balance_before, balance_after, delta, source, details) " +
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)";

            try (PreparedStatement stmt = conn.prepareStatement(sql)) {
                for (BalanceChange change : changes) {
                    stmt.setString(1, change.getPlayerUuid().toString());
                    stmt.setString(2, change.getPlayerName());
                    stmt.setLong(3, change.getTimestampMs());
                    stmt.setDouble(4, change.getBalanceBefore());
                    stmt.setDouble(5, change.getBalanceAfter());
                    stmt.setDouble(6, change.getDelta());
                    stmt.setString(7, change.getSource().name());
                    stmt.setString(8, change.getDetails());
                    stmt.addBatch();
                }

                stmt.executeBatch();
            }
        });

        plugin.getLogger().fine("Wrote batch of " + changes.size() + " balance changes");
    }

    public int getQueueSize() {
        return writeQueue.size();
    }

    public boolean isRunning() {
        return running;
    }
}
