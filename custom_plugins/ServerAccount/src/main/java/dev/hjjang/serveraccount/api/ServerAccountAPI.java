package dev.hjjang.serveraccount.api;

import dev.hjjang.serveraccount.ServerAccountPlugin;

/**
 * Static API for other plugins to deposit to the server account.
 * Called via reflection from plugins that don't want a compile-time dependency.
 */
public class ServerAccountAPI {
    private static ServerAccountPlugin plugin;

    public static void init(ServerAccountPlugin pluginInstance) {
        plugin = pluginInstance;
    }

    /**
     * Deposit money into the server account with logging.
     *
     * @param amount Amount to deposit
     * @param sourcePlugin Name of the plugin making the deposit (e.g., "ServerShop", "UltraCosmetics")
     * @param playerName Player associated with this transaction (nullable)
     * @param details Description of the transaction (nullable)
     * @return true if successful
     */
    public static boolean deposit(double amount, String sourcePlugin, String playerName, String details) {
        if (plugin == null || !plugin.isEnabled()) {
            return false;
        }
        return plugin.getAccountManager().deposit(amount, sourcePlugin, playerName, details);
    }

    /**
     * Check if the ServerAccount API is available.
     */
    public static boolean isAvailable() {
        return plugin != null && plugin.isEnabled();
    }
}
