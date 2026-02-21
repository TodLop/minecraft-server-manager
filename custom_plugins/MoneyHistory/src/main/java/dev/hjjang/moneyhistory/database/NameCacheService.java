package dev.hjjang.moneyhistory.database;

import dev.hjjang.moneyhistory.MoneyHistoryPlugin;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class NameCacheService implements Listener {
    private final MoneyHistoryPlugin plugin;
    private final DatabaseManager databaseManager;
    private final ConcurrentHashMap<UUID, String> nameCache;

    public NameCacheService(MoneyHistoryPlugin plugin, DatabaseManager databaseManager) {
        this.plugin = plugin;
        this.databaseManager = databaseManager;
        this.nameCache = new ConcurrentHashMap<>();
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPlayerJoin(PlayerJoinEvent event) {
        Player player = event.getPlayer();
        updatePlayerName(player.getUniqueId(), player.getName());
    }

    public void updatePlayerName(UUID uuid, String name) {
        // Update memory cache
        nameCache.put(uuid, name);

        // Update database asynchronously
        plugin.getServer().getScheduler().runTaskAsynchronously(plugin, () -> {
            try {
                updatePlayerNameInDatabase(uuid, name);
            } catch (SQLException e) {
                plugin.getLogger().warning("Failed to update player name in database: " + e.getMessage());
            }
        });
    }

    private void updatePlayerNameInDatabase(UUID uuid, String name) throws SQLException {
        long now = System.currentTimeMillis();

        try (Connection conn = databaseManager.getConnection()) {
            // Check if player exists
            String checkSql = "SELECT player_name FROM player_names WHERE player_uuid = ?";
            try (PreparedStatement stmt = conn.prepareStatement(checkSql)) {
                stmt.setString(1, uuid.toString());
                try (ResultSet rs = stmt.executeQuery()) {
                    if (rs.next()) {
                        // Update existing record
                        String updateSql = "UPDATE player_names SET player_name = ?, last_seen = ? WHERE player_uuid = ?";
                        try (PreparedStatement updateStmt = conn.prepareStatement(updateSql)) {
                            updateStmt.setString(1, name);
                            updateStmt.setLong(2, now);
                            updateStmt.setString(3, uuid.toString());
                            updateStmt.executeUpdate();
                        }
                    } else {
                        // Insert new record
                        String insertSql = "INSERT INTO player_names (player_uuid, player_name, first_seen, last_seen) VALUES (?, ?, ?, ?)";
                        try (PreparedStatement insertStmt = conn.prepareStatement(insertSql)) {
                            insertStmt.setString(1, uuid.toString());
                            insertStmt.setString(2, name);
                            insertStmt.setLong(3, now);
                            insertStmt.setLong(4, now);
                            insertStmt.executeUpdate();
                        }
                    }
                }
            }
        }
    }

    public void updateLastBalance(UUID uuid, double balance) {
        plugin.getServer().getScheduler().runTaskAsynchronously(plugin, () -> {
            try {
                String sql = "UPDATE player_names SET last_balance = ? WHERE player_uuid = ?";
                try (Connection conn = databaseManager.getConnection();
                     PreparedStatement stmt = conn.prepareStatement(sql)) {
                    stmt.setDouble(1, balance);
                    stmt.setString(2, uuid.toString());
                    stmt.executeUpdate();
                }
            } catch (SQLException e) {
                plugin.getLogger().warning("Failed to update last balance: " + e.getMessage());
            }
        });
    }

    public String getPlayerName(UUID uuid) {
        // Check memory cache first
        String cached = nameCache.get(uuid);
        if (cached != null) {
            return cached;
        }

        // Query database
        try (Connection conn = databaseManager.getConnection()) {
            String sql = "SELECT player_name FROM player_names WHERE player_uuid = ?";
            try (PreparedStatement stmt = conn.prepareStatement(sql)) {
                stmt.setString(1, uuid.toString());
                try (ResultSet rs = stmt.executeQuery()) {
                    if (rs.next()) {
                        String name = rs.getString("player_name");
                        nameCache.put(uuid, name);
                        return name;
                    }
                }
            }
        } catch (SQLException e) {
            plugin.getLogger().warning("Failed to query player name: " + e.getMessage());
        }

        return null;
    }

    public Double getLastBalance(UUID uuid) {
        try (Connection conn = databaseManager.getConnection()) {
            String sql = "SELECT last_balance FROM player_names WHERE player_uuid = ?";
            try (PreparedStatement stmt = conn.prepareStatement(sql)) {
                stmt.setString(1, uuid.toString());
                try (ResultSet rs = stmt.executeQuery()) {
                    if (rs.next()) {
                        double balance = rs.getDouble("last_balance");
                        return rs.wasNull() ? null : balance;
                    }
                }
            }
        } catch (SQLException e) {
            plugin.getLogger().warning("Failed to query last balance: " + e.getMessage());
        }

        return null;
    }

    public void clearCache() {
        nameCache.clear();
    }
}
