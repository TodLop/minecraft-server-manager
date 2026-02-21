package com.nearoutpost.servershop;

import net.luckperms.api.LuckPerms;
import net.luckperms.api.model.user.User;
import net.luckperms.api.node.Node;
import org.bukkit.plugin.RegisteredServiceProvider;
import org.bukkit.plugin.java.JavaPlugin;

import java.util.UUID;
import java.util.concurrent.CompletableFuture;

/**
 * Wrapper class for LuckPerms API integration.
 * Handles permission granting and checking for sethome slots.
 */
public class LuckPermsIntegration {

    private final JavaPlugin plugin;
    private LuckPerms luckPerms = null;

    public LuckPermsIntegration(JavaPlugin plugin) {
        this.plugin = plugin;
    }

    /**
     * Initialize LuckPerms API connection.
     * Must be called in onEnable after LuckPerms is loaded.
     *
     * @return true if LuckPerms was successfully initialized
     */
    public boolean setupLuckPerms() {
        if (plugin.getServer().getPluginManager().getPlugin("LuckPerms") == null) {
            return false;
        }

        RegisteredServiceProvider<LuckPerms> provider = plugin.getServer().getServicesManager().getRegistration(LuckPerms.class);
        if (provider == null) {
            return false;
        }

        luckPerms = provider.getProvider();
        return luckPerms != null;
    }

    /**
     * Grant a permission node to a player.
     * This method is synchronous and will block until the permission is granted.
     *
     * @param playerUuid UUID of the player
     * @param permission Permission node to grant (e.g., "essentials.sethome.multiple.homes4")
     * @return true if permission was successfully granted
     */
    public boolean grantPermission(UUID playerUuid, String permission) {
        if (luckPerms == null) {
            plugin.getLogger().severe("LuckPerms not initialized! Cannot grant permission.");
            return false;
        }

        try {
            // Load user (this returns a CompletableFuture)
            CompletableFuture<User> userFuture = luckPerms.getUserManager().loadUser(playerUuid);

            // Wait for user to load and grant permission
            User user = userFuture.join(); // Block until loaded

            // Create permission node
            Node node = Node.builder(permission).build();

            // Add permission to user
            user.data().add(node);

            // Save user data
            luckPerms.getUserManager().saveUser(user);

            plugin.getLogger().info("Granted permission '" + permission + "' to player " + playerUuid);
            return true;

        } catch (Exception e) {
            plugin.getLogger().severe("Failed to grant permission '" + permission + "' to player " + playerUuid + ": " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }

    /**
     * Check if a player has a specific permission node.
     * Note: This checks the LuckPerms data directly, not Bukkit's permission system.
     *
     * @param playerUuid UUID of the player
     * @param permission Permission node to check
     * @return true if the player has the permission
     */
    public boolean hasPermission(UUID playerUuid, String permission) {
        if (luckPerms == null) {
            plugin.getLogger().warning("LuckPerms not initialized! Cannot check permission.");
            return false;
        }

        try {
            // Try to get cached user first
            User user = luckPerms.getUserManager().getUser(playerUuid);

            if (user == null) {
                // User not cached, load them
                user = luckPerms.getUserManager().loadUser(playerUuid).join();
            }

            return user.getCachedData().getPermissionData().checkPermission(permission).asBoolean();

        } catch (Exception e) {
            plugin.getLogger().warning("Failed to check permission for player " + playerUuid + ": " + e.getMessage());
            return false;
        }
    }

    /**
     * Check if LuckPerms is available and initialized.
     *
     * @return true if LuckPerms API is available
     */
    public boolean isAvailable() {
        return luckPerms != null;
    }

    /**
     * Get the LuckPerms API instance.
     *
     * @return LuckPerms API instance, or null if not initialized
     */
    public LuckPerms getApi() {
        return luckPerms;
    }
}
