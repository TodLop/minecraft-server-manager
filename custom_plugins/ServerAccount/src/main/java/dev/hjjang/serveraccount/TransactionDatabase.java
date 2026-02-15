package dev.hjjang.serveraccount;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import java.io.File;
import java.sql.*;
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Logger;

public class TransactionDatabase {
    private final HikariDataSource dataSource;
    private final Logger logger;

    public TransactionDatabase(File dataFolder, Logger logger) {
        this.logger = logger;

        File dbFile = new File(dataFolder, "transactions.db");

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:sqlite:" + dbFile.getAbsolutePath());
        config.setMaximumPoolSize(3);
        config.setPoolName("ServerAccount-DB");
        config.setConnectionTestQuery("SELECT 1");

        this.dataSource = new HikariDataSource(config);

        initializeTable();
    }

    private void initializeTable() {
        try (Connection conn = dataSource.getConnection();
             Statement stmt = conn.createStatement()) {
            stmt.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_ms INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    source_plugin TEXT,
                    player_name TEXT,
                    admin_name TEXT,
                    reason TEXT,
                    balance_after REAL NOT NULL
                )
            """);
            stmt.execute("CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp_ms DESC)");
        } catch (SQLException e) {
            logger.severe("Failed to initialize transaction database: " + e.getMessage());
        }
    }

    public void recordTransaction(String type, double amount, String sourcePlugin,
                                  String playerName, String adminName, String reason,
                                  double balanceAfter) {
        String sql = "INSERT INTO transactions (timestamp_ms, type, amount, source_plugin, player_name, admin_name, reason, balance_after) VALUES (?, ?, ?, ?, ?, ?, ?, ?)";
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, System.currentTimeMillis());
            ps.setString(2, type);
            ps.setDouble(3, amount);
            ps.setString(4, sourcePlugin);
            ps.setString(5, playerName);
            ps.setString(6, adminName);
            ps.setString(7, reason);
            ps.setDouble(8, balanceAfter);
            ps.executeUpdate();
        } catch (SQLException e) {
            logger.severe("Failed to record transaction: " + e.getMessage());
        }
    }

    public List<TransactionRecord> getHistory(int page, int perPage) {
        List<TransactionRecord> records = new ArrayList<>();
        int offset = (page - 1) * perPage;

        String sql = "SELECT id, timestamp_ms, type, amount, source_plugin, player_name, admin_name, reason, balance_after FROM transactions ORDER BY timestamp_ms DESC LIMIT ? OFFSET ?";
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setInt(1, perPage);
            ps.setInt(2, offset);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    records.add(new TransactionRecord(
                        rs.getInt("id"),
                        rs.getLong("timestamp_ms"),
                        rs.getString("type"),
                        rs.getDouble("amount"),
                        rs.getString("source_plugin"),
                        rs.getString("player_name"),
                        rs.getString("admin_name"),
                        rs.getString("reason"),
                        rs.getDouble("balance_after")
                    ));
                }
            }
        } catch (SQLException e) {
            logger.severe("Failed to query transaction history: " + e.getMessage());
        }

        return records;
    }

    public int getTotalCount() {
        try (Connection conn = dataSource.getConnection();
             Statement stmt = conn.createStatement();
             ResultSet rs = stmt.executeQuery("SELECT COUNT(*) FROM transactions")) {
            if (rs.next()) {
                return rs.getInt(1);
            }
        } catch (SQLException e) {
            logger.severe("Failed to get transaction count: " + e.getMessage());
        }
        return 0;
    }

    public void close() {
        if (dataSource != null && !dataSource.isClosed()) {
            dataSource.close();
        }
    }
}
