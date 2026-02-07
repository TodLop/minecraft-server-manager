package com.nearoutpost.servershop;

import net.milkbowl.vault.economy.Economy;
import net.milkbowl.vault.economy.EconomyResponse;
import org.bukkit.ChatColor;
import org.bukkit.entity.Player;

/**
 * Handles the purchase flow for anvil access.
 */
public class AnvilAccessHandler {

    private final ServerShop plugin;

    public AnvilAccessHandler(ServerShop plugin) {
        this.plugin = plugin;
    }

    /**
     * Process anvil access purchase for a player.
     *
     * @param player Player attempting to purchase
     * @return true if command was handled (doesn't mean purchase succeeded)
     */
    public boolean purchase(Player player) {
        // Check if feature is enabled
        if (!plugin.getConfig().getBoolean("anvil_access.enabled", true)) {
            player.sendMessage(colorize(getMessage("anvil-feature-disabled")));
            return true;
        }

        // Get permission node from config
        String permission = plugin.getConfig().getString("anvil_access.permission", "servershop.anvil.use");

        // Check if player already has permission
        if (player.hasPermission(permission)) {
            player.sendMessage(colorize(getMessage("anvil-already-owned")));
            return true;
        }

        // Get price from config
        int price = plugin.getConfig().getInt("anvil_access.price", 500000);

        // Check balance
        Economy economy = ServerShop.getEconomy();
        double balance = economy.getBalance(player);

        if (balance < price) {
            player.sendMessage(colorize(getMessage("not-enough-money")
                    .replace("%price%", String.format("%.0f", (double) price))
                    .replace("%balance%", String.format("%.0f", balance))));
            return true;
        }

        // Withdraw money
        EconomyResponse response = economy.withdrawPlayer(player, price);

        if (!response.transactionSuccess()) {
            player.sendMessage(colorize("&c거래 실패: " + response.errorMessage));
            plugin.getLogger().severe("Vault withdrawal failed for " + player.getName() + ": " + response.errorMessage);
            return true;
        }

        // Grant permission via LuckPerms
        LuckPermsIntegration luckPerms = plugin.getLuckPermsIntegration();
        if (!luckPerms.isAvailable()) {
            // Refund - LuckPerms not available
            economy.depositPlayer(player, price);
            player.sendMessage(colorize("&cLuckPerms 연동 오류! 돈이 반환되었습니다."));
            plugin.getLogger().severe("LuckPerms not available! Purchase cancelled.");
            return true;
        }

        boolean permissionGranted = luckPerms.grantPermission(player.getUniqueId(), permission);

        if (!permissionGranted) {
            // Refund - permission grant failed
            economy.depositPlayer(player, price);
            player.sendMessage(colorize("&c권한 부여 실패! 돈이 반환되었습니다."));
            plugin.getLogger().severe("Failed to grant anvil permission to " + player.getName() + "! Purchase cancelled and refunded.");
            return true;
        }

        // Success!
        player.sendMessage(colorize(getMessage("anvil-purchased")
                .replace("%price%", String.format("%.0f", (double) price))));

        // Log to console
        plugin.getLogger().info(player.getName() + " purchased anvil access for " + price + " (permission: " + permission + ")");

        return true;
    }

    /**
     * Show information about anvil access purchase.
     *
     * @param player Player to show info to
     * @return true (command handled)
     */
    public boolean showInfo(Player player) {
        // Check if feature is enabled
        if (!plugin.getConfig().getBoolean("anvil_access.enabled", true)) {
            player.sendMessage(colorize(getMessage("anvil-feature-disabled")));
            return true;
        }

        // Get permission node from config
        String permission = plugin.getConfig().getString("anvil_access.permission", "servershop.anvil.use");

        // Check if player already has permission
        if (player.hasPermission(permission)) {
            player.sendMessage(colorize(getMessage("anvil-already-owned")));
            return true;
        }

        // Get price from config
        int price = plugin.getConfig().getInt("anvil_access.price", 500000);

        player.sendMessage(colorize(getMessage("anvil-price-info")
                .replace("%price%", String.format("%.0f", (double) price))));

        return true;
    }

    private String getMessage(String key) {
        String prefix = plugin.getConfig().getString("messages.prefix", "&6[서버상점] &r");
        String message = plugin.getConfig().getString("messages." + key, "&cMessage not found: " + key);
        return prefix + message;
    }

    private String colorize(String message) {
        return ChatColor.translateAlternateColorCodes('&', message);
    }
}
