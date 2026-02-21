package dev.hjjang.moneyhistory.database;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import dev.hjjang.moneyhistory.MoneyHistoryPlugin;

import java.io.File;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public class DatabaseManager {
    private final MoneyHistoryPlugin plugin;
    private final File databaseFile;
    private HikariDataSource dataSource;

    public DatabaseManager(MoneyHistoryPlugin plugin) {
        this.plugin = plugin;
        this.databaseFile = new File(plugin.getDataFolder(), "history.db");
    }

    public void initialize() throws SQLException {
        // Ensure plugin data folder exists
        if (!plugin.getDataFolder().exists()) {
            plugin.getDataFolder().mkdirs();
        }

        // Setup HikariCP connection pool
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:sqlite:" + databaseFile.getAbsolutePath());
        config.setMaximumPoolSize(3);
        config.setConnectionTimeout(5000);
        config.setIdleTimeout(600000);
        config.setMaxLifetime(1800000);

        // SQLite specific settings
        config.addDataSourceProperty("journal_mode", "WAL");
        config.addDataSourceProperty("synchronous", "NORMAL");
        config.addDataSourceProperty("cache_size", "10000");

        dataSource = new HikariDataSource(config);

        // Initialize schema
        initializeSchema();

        // Verify database integrity
        verifyIntegrity();

        plugin.getLogger().info("Database file: " + databaseFile.getAbsolutePath());
    }

    private void initializeSchema() throws SQLException {
        try (Connection conn = getConnection()) {
            try (Statement stmt = conn.createStatement()) {
                // Enable WAL mode
                stmt.execute("PRAGMA journal_mode=WAL");
                stmt.execute("PRAGMA synchronous=NORMAL");

                // Create balance_history table
                stmt.execute(
                    "CREATE TABLE IF NOT EXISTS balance_history (" +
                    "    id INTEGER PRIMARY KEY AUTOINCREMENT," +
                    "    player_uuid TEXT NOT NULL," +
                    "    player_name TEXT NOT NULL," +
                    "    timestamp_ms INTEGER NOT NULL," +
                    "    balance_before REAL NOT NULL," +
                    "    balance_after REAL NOT NULL," +
                    "    delta REAL NOT NULL," +
                    "    source TEXT NOT NULL," +
                    "    details TEXT," +
                    "    CHECK(delta = balance_after - balance_before)" +
                    ")"
                );

                // Create player_names table
                stmt.execute(
                    "CREATE TABLE IF NOT EXISTS player_names (" +
                    "    player_uuid TEXT PRIMARY KEY," +
                    "    player_name TEXT NOT NULL," +
                    "    first_seen INTEGER NOT NULL," +
                    "    last_seen INTEGER NOT NULL," +
                    "    last_balance REAL" +
                    ")"
                );

                // Create plugin_metadata table
                stmt.execute(
                    "CREATE TABLE IF NOT EXISTS plugin_metadata (" +
                    "    key TEXT PRIMARY KEY," +
                    "    value TEXT NOT NULL" +
                    ")"
                );

                // Create indexes
                stmt.execute(
                    "CREATE INDEX IF NOT EXISTS idx_player_time " +
                    "ON balance_history(player_uuid, timestamp_ms DESC)"
                );

                stmt.execute(
                    "CREATE INDEX IF NOT EXISTS idx_timestamp " +
                    "ON balance_history(timestamp_ms DESC)"
                );

                stmt.execute(
                    "CREATE INDEX IF NOT EXISTS idx_source " +
                    "ON balance_history(source)"
                );

                // Insert initial metadata
                stmt.execute(
                    "INSERT OR IGNORE INTO plugin_metadata (key, value) " +
                    "VALUES ('schema_version', '1')"
                );

                stmt.execute(
                    "INSERT OR IGNORE INTO plugin_metadata (key, value) " +
                    "VALUES ('created_at', '" + System.currentTimeMillis() + "')"
                );
            }
        }

        plugin.getLogger().info("Database schema initialized");
    }

    private void verifyIntegrity() throws SQLException {
        try (Connection conn = getConnection();
             Statement stmt = conn.createStatement();
             ResultSet rs = stmt.executeQuery("PRAGMA integrity_check")) {

            if (rs.next()) {
                String result = rs.getString(1);
                if (!"ok".equalsIgnoreCase(result)) {
                    throw new SQLException("Database integrity check failed: " + result);
                }
            }
        }

        plugin.getLogger().info("Database integrity verified");
    }

    public Connection getConnection() throws SQLException {
        if (dataSource == null || dataSource.isClosed()) {
            throw new SQLException("Database connection pool is not initialized");
        }
        return dataSource.getConnection();
    }

    public void close() {
        if (dataSource != null && !dataSource.isClosed()) {
            dataSource.close();
            plugin.getLogger().info("Database connection pool closed");
        }
    }

    public File getDatabaseFile() {
        return databaseFile;
    }

    public boolean isConnected() {
        return dataSource != null && !dataSource.isClosed();
    }

    // Utility method for transaction-safe batch operations
    public void executeBatch(BatchOperation operation) throws SQLException {
        try (Connection conn = getConnection()) {
            conn.setAutoCommit(false);
            try {
                operation.execute(conn);
                conn.commit();
            } catch (SQLException e) {
                conn.rollback();
                throw e;
            } finally {
                conn.setAutoCommit(true);
            }
        }
    }

    @FunctionalInterface
    public interface BatchOperation {
        void execute(Connection conn) throws SQLException;
    }
}
