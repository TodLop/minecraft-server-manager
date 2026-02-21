package com.nearoutpost.servershop;

import com.earth2me.essentials.Essentials;
import com.earth2me.essentials.User;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;

/**
 * Wrapper class for EssentialsX API integration.
 * Handles nickname setting and retrieval with fallback to console commands.
 */
public class EssentialsIntegration {

    private final ServerShop plugin;
    private Essentials essentials = null;

    public EssentialsIntegration(ServerShop plugin) {
        this.plugin = plugin;
    }

    /**
     * Initialize EssentialsX API connection.
     * Must be called in onEnable after Essentials is loaded.
     *
     * @return true if Essentials was successfully initialized
     */
    public boolean setupEssentials() {
        Plugin essentialsPlugin = plugin.getServer().getPluginManager().getPlugin("Essentials");
        if (essentialsPlugin == null) {
            return false;
        }

        if (!(essentialsPlugin instanceof Essentials)) {
            plugin.getLogger().warning("Essentials plugin found but wrong type!");
            return false;
        }

        essentials = (Essentials) essentialsPlugin;
        return true;
    }

    /**
     * Set a player's nickname using EssentialsX.
     * Attempts API first, falls back to console command if API fails.
     *
     * @param player The player to set nickname for
     * @param nickname The nickname to set (may include color codes)
     * @return true if nickname was successfully set
     */
    public boolean setNickname(Player player, String nickname) {
        if (essentials == null) {
            plugin.getLogger().warning("Essentials not initialized! Cannot set nickname.");
            return false;
        }

        try {
            // Try API method first (preferred)
            User user = essentials.getUser(player);
            if (user != null) {
                user.setNickname(nickname);
                plugin.getLogger().info("Set nickname for " + player.getName() + " to '" + nickname + "' via API");
                return true;
            } else {
                plugin.getLogger().warning("Could not get Essentials user for " + player.getName());
            }
        } catch (Exception e) {
            plugin.getLogger().warning("Failed to set nickname via API, trying console command: " + e.getMessage());
        }

        // Fallback to console command
        try {
            String command = "essentials:nick " + player.getName() + " " + nickname;
            boolean success = Bukkit.dispatchCommand(Bukkit.getConsoleSender(), command);

            if (success) {
                plugin.getLogger().info("Set nickname for " + player.getName() + " to '" + nickname + "' via console command");
            } else {
                plugin.getLogger().warning("Console command failed to set nickname for " + player.getName());
            }

            return success;
        } catch (Exception e) {
            plugin.getLogger().severe("Failed to set nickname via console command: " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }

    /**
     * Clear a player's nickname, resetting it to their username.
     *
     * @param player The player to clear nickname for
     * @return true if nickname was successfully cleared
     */
    public boolean clearNickname(Player player) {
        if (essentials == null) {
            plugin.getLogger().warning("Essentials not initialized! Cannot clear nickname.");
            return false;
        }

        try {
            User user = essentials.getUser(player);
            if (user != null) {
                user.setNickname(null);
                plugin.getLogger().info("Cleared nickname for " + player.getName() + " via API");
                return true;
            } else {
                plugin.getLogger().warning("Could not get Essentials user for " + player.getName());
            }
        } catch (Exception e) {
            plugin.getLogger().warning("Failed to clear nickname via API, trying console command: " + e.getMessage());
        }

        // Fallback to console command
        try {
            String command = "essentials:nick " + player.getName() + " off";
            boolean success = Bukkit.dispatchCommand(Bukkit.getConsoleSender(), command);

            if (success) {
                plugin.getLogger().info("Cleared nickname for " + player.getName() + " via console command");
            } else {
                plugin.getLogger().warning("Console command failed to clear nickname for " + player.getName());
            }

            return success;
        } catch (Exception e) {
            plugin.getLogger().severe("Failed to clear nickname via console command: " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }

    /**
     * Get a player's current nickname from EssentialsX.
     *
     * @param player The player to get nickname for
     * @return The player's nickname, or their username if no nickname set
     */
    public String getNickname(Player player) {
        if (essentials == null) {
            return player.getName();
        }

        try {
            User user = essentials.getUser(player);
            if (user != null) {
                String nickname = user.getNickname();
                return (nickname != null && !nickname.isEmpty()) ? nickname : player.getName();
            }
        } catch (Exception e) {
            plugin.getLogger().warning("Failed to get nickname for " + player.getName() + ": " + e.getMessage());
        }

        return player.getName();
    }

    /**
     * Check if Essentials is available and initialized.
     *
     * @return true if Essentials API is available
     */
    public boolean isAvailable() {
        return essentials != null;
    }

    /**
     * Get the Essentials API instance.
     *
     * @return Essentials API instance, or null if not initialized
     */
    public Essentials getApi() {
        return essentials;
    }
}
