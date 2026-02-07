package com.nearoutpost.servershop;

import net.milkbowl.vault.economy.Economy;
import net.milkbowl.vault.economy.EconomyResponse;
import org.bukkit.ChatColor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

/**
 * Handles the purchase flow for nickname changes.
 * Follows transaction safety pattern: validate before charge, refund on failure.
 */
public class NicknameChangeHandler {

    private final ServerShop plugin;
    private final NicknameValidator validator;
    private final NicknameCooldownManager cooldownManager;

    public NicknameChangeHandler(ServerShop plugin) {
        this.plugin = plugin;
        this.validator = new NicknameValidator(plugin);
        this.cooldownManager = new NicknameCooldownManager(plugin);
    }

    /**
     * Process a nickname purchase for a player.
     *
     * @param player Player attempting to purchase
     * @param newNickname The desired nickname
     * @return true if command was handled (doesn't mean purchase succeeded)
     */
    public boolean purchase(Player player, String newNickname) {
        // Check if feature is enabled
        if (!plugin.getConfig().getBoolean("nickname_shop.enabled", true)) {
            player.sendMessage(colorize(getMessage("nickname-feature-disabled")));
            return true;
        }

        // Check if Essentials is available
        EssentialsIntegration essentials = plugin.getEssentialsIntegration();
        if (essentials == null || !essentials.isAvailable()) {
            player.sendMessage(colorize(getMessage("nickname-essentials-not-found")));
            return true;
        }

        // Validate nickname BEFORE charging money
        NicknameValidator.ValidationResult validation = validator.validate(newNickname);
        if (!validation.isValid()) {
            String errorMessage = getMessage(validation.getErrorMessageKey())
                    .replace("{min_length}", String.valueOf(validator.getMinLength()))
                    .replace("{max_length}", String.valueOf(validator.getMaxLength()));
            player.sendMessage(colorize(errorMessage));
            return true;
        }

        // Check cooldown BEFORE charging money
        if (cooldownManager.isOnCooldown(player.getUniqueId())) {
            long remaining = cooldownManager.getRemainingCooldown(player.getUniqueId());
            String formattedTime = NicknameCooldownManager.formatDuration(remaining);
            player.sendMessage(colorize(getMessage("nickname-cooldown-active")
                    .replace("{remaining}", formattedTime)));
            return true;
        }

        // Get price and check balance
        double price = plugin.getConfig().getDouble("nickname_shop.price", 10000);
        Economy economy = ServerShop.getEconomy();
        double balance = economy.getBalance(player);

        if (balance < price) {
            player.sendMessage(colorize(getMessage("nickname-cannot-afford")
                    .replace("{price}", String.format("%.0f", price))
                    .replace("{balance}", String.format("%.0f", balance))));
            return true;
        }

        // Withdraw money
        EconomyResponse response = economy.withdrawPlayer(player, price);

        if (!response.transactionSuccess()) {
            player.sendMessage(colorize("&c거래 실패: " + response.errorMessage));
            plugin.getLogger().severe("Vault withdrawal failed for " + player.getName() + ": " + response.errorMessage);
            return true;
        }

        // Capture current nickname before change
        String currentNickname = essentials.getNickname(player);

        // Attempt nickname change
        boolean success = essentials.setNickname(player, newNickname);

        if (!success) {
            // REFUND - nickname change failed
            economy.depositPlayer(player, price);
            player.sendMessage(colorize("&c닉네임 변경 실패! 돈이 반환되었습니다."));
            plugin.getLogger().severe("Failed to set nickname for " + player.getName() + "! Purchase cancelled and refunded.");
            return true;
        }

        // Success! Set cooldown
        String cooldownDuration = plugin.getConfig().getString("nickname_shop.cooldown", "7d");
        try {
            long cooldownMillis = NicknameCooldownManager.parseDuration(cooldownDuration);
            cooldownManager.setCooldown(player.getUniqueId(), cooldownMillis);
        } catch (IllegalArgumentException e) {
            plugin.getLogger().warning("Invalid cooldown duration in config: " + cooldownDuration);
            // Continue anyway - purchase succeeded
        }

        // Send success message
        player.sendMessage(colorize(getMessage("nickname-success")
                .replace("{nickname}", ChatColor.translateAlternateColorCodes('&', newNickname))
                .replace("{price}", String.format("%.0f", price))));

        // Log to console with improved format
        plugin.getLogger().info(player.getName() + " (" + currentNickname + ") purchased nickname change to '" + newNickname + "' for " + price);

        return true;
    }

    /**
     * Show information about player's current nickname and cooldown status.
     *
     * @param player Player to show info to
     * @return true (command handled)
     */
    public boolean showInfo(Player player) {
        // Check if feature is enabled
        if (!plugin.getConfig().getBoolean("nickname_shop.enabled", true)) {
            player.sendMessage(colorize(getMessage("nickname-feature-disabled")));
            return true;
        }

        // Check if Essentials is available
        EssentialsIntegration essentials = plugin.getEssentialsIntegration();
        if (essentials == null || !essentials.isAvailable()) {
            player.sendMessage(colorize(getMessage("nickname-essentials-not-found")));
            return true;
        }

        // Get current nickname
        String currentNickname = essentials.getNickname(player);
        player.sendMessage(colorize(getMessage("nickname-current-nickname")
                .replace("{nickname}", ChatColor.translateAlternateColorCodes('&', currentNickname))));

        // Check cooldown status
        if (cooldownManager.isOnCooldown(player.getUniqueId())) {
            long remaining = cooldownManager.getRemainingCooldown(player.getUniqueId());
            String formattedTime = NicknameCooldownManager.formatDuration(remaining);
            player.sendMessage(colorize(getMessage("nickname-cooldown-info")
                    .replace("{remaining}", formattedTime)));
        } else {
            player.sendMessage(colorize(getMessage("nickname-no-cooldown")));
        }

        return true;
    }

    /**
     * Reset a player's nickname back to their username.
     * Respects cooldown (no cost).
     *
     * @param player Player requesting nickname reset
     * @return true (command handled)
     */
    public boolean resetNickname(Player player) {
        // Check if feature is enabled
        if (!plugin.getConfig().getBoolean("nickname_shop.enabled", true)) {
            player.sendMessage(colorize(getMessage("nickname-feature-disabled")));
            return true;
        }

        // Check if Essentials is available
        EssentialsIntegration essentials = plugin.getEssentialsIntegration();
        if (essentials == null || !essentials.isAvailable()) {
            player.sendMessage(colorize(getMessage("nickname-essentials-not-found")));
            return true;
        }

        // Check cooldown
        if (cooldownManager.isOnCooldown(player.getUniqueId())) {
            long remaining = cooldownManager.getRemainingCooldown(player.getUniqueId());
            String formattedTime = NicknameCooldownManager.formatDuration(remaining);
            player.sendMessage(colorize(getMessage("nickname-cooldown-active")
                    .replace("{remaining}", formattedTime)));
            return true;
        }

        // Capture current nickname before reset
        String currentNickname = essentials.getNickname(player);

        // Clear nickname
        boolean success = essentials.clearNickname(player);

        if (!success) {
            player.sendMessage(colorize("&c닉네임 초기화 실패!"));
            return true;
        }

        // Set cooldown
        String cooldownDuration = plugin.getConfig().getString("nickname_shop.cooldown", "7d");
        try {
            long cooldownMillis = NicknameCooldownManager.parseDuration(cooldownDuration);
            cooldownManager.setCooldown(player.getUniqueId(), cooldownMillis);
        } catch (IllegalArgumentException e) {
            plugin.getLogger().warning("Invalid cooldown duration in config: " + cooldownDuration);
        }

        player.sendMessage(colorize(getMessage("nickname-reset-success")));

        // Log to console
        plugin.getLogger().info(player.getName() + " (" + currentNickname + ") reset their nickname to default");

        return true;
    }

    /**
     * Admin command: Reset a target player's nickname back to their username.
     * Bypasses cooldown.
     *
     * @param sender Command sender (console or admin player)
     * @param targetName Target player name
     * @return true (command handled)
     */
    public boolean adminResetNickname(CommandSender sender, String targetName) {
        // Check if Essentials is available
        EssentialsIntegration essentials = plugin.getEssentialsIntegration();
        if (essentials == null || !essentials.isAvailable()) {
            sender.sendMessage(colorize(getMessage("nickname-essentials-not-found")));
            return true;
        }

        // Find player
        Player target = plugin.getServer().getPlayerExact(targetName);
        if (target == null) {
            sender.sendMessage(colorize(getMessage("nickname-admin-player-not-found")
                    .replace("{player}", targetName)));
            return true;
        }

        // Capture current nickname
        String currentNickname = essentials.getNickname(target);

        // Clear nickname
        boolean success = essentials.clearNickname(target);

        if (success) {
            sender.sendMessage(colorize(getMessage("nickname-admin-reset-success")
                    .replace("{player}", target.getName())));
            plugin.getLogger().info(sender.getName() + " admin-reset nickname for " + target.getName() + " (was '" + currentNickname + "')");
        } else {
            sender.sendMessage(colorize("&c닉네임 초기화 실패!"));
        }

        return true;
    }

    /**
     * Admin command: Set a player's nickname bypassing price and cooldown.
     *
     * @param sender Command sender (console or admin player)
     * @param targetName Target player name
     * @param nickname Nickname to set
     * @return true (command handled)
     */
    public boolean adminSetNickname(CommandSender sender, String targetName, String nickname) {
        // Check if Essentials is available
        EssentialsIntegration essentials = plugin.getEssentialsIntegration();
        if (essentials == null || !essentials.isAvailable()) {
            sender.sendMessage(colorize(getMessage("nickname-essentials-not-found")));
            return true;
        }

        // Find player
        Player target = plugin.getServer().getPlayerExact(targetName);
        if (target == null) {
            sender.sendMessage(colorize(getMessage("nickname-admin-player-not-found")
                    .replace("{player}", targetName)));
            return true;
        }

        // Validate nickname (still apply rules even for admin)
        NicknameValidator.ValidationResult validation = validator.validate(nickname);
        if (!validation.isValid()) {
            String errorMessage = getMessage(validation.getErrorMessageKey())
                    .replace("{min_length}", String.valueOf(validator.getMinLength()))
                    .replace("{max_length}", String.valueOf(validator.getMaxLength()));
            sender.sendMessage(colorize(errorMessage));
            return true;
        }

        // Capture current nickname
        String currentNickname = essentials.getNickname(target);

        // Set nickname
        boolean success = essentials.setNickname(target, nickname);

        if (success) {
            sender.sendMessage(colorize(getMessage("nickname-admin-set-success")
                    .replace("{player}", target.getName())
                    .replace("{nickname}", ChatColor.translateAlternateColorCodes('&', nickname))));
            plugin.getLogger().info(sender.getName() + " admin-set nickname for " + target.getName() + " (" + currentNickname + ") to '" + nickname + "'");
        } else {
            sender.sendMessage(colorize("&c닉네임 설정 실패!"));
        }

        return true;
    }

    /**
     * Admin command: Reset a player's nickname cooldown.
     *
     * @param sender Command sender (console or admin player)
     * @param targetName Target player name
     * @return true (command handled)
     */
    public boolean adminResetCooldown(CommandSender sender, String targetName) {
        // Find player
        Player target = plugin.getServer().getPlayerExact(targetName);
        if (target == null) {
            sender.sendMessage(colorize(getMessage("nickname-admin-player-not-found")
                    .replace("{player}", targetName)));
            return true;
        }

        // Reset cooldown
        cooldownManager.removeCooldown(target.getUniqueId());

        sender.sendMessage(colorize(getMessage("nickname-admin-cooldown-reset")
                .replace("{player}", target.getName())));
        plugin.getLogger().info(sender.getName() + " reset nickname cooldown for " + target.getName());

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
