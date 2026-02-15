package com.nearoutpost.servershop;

import net.milkbowl.vault.economy.Economy;
import net.milkbowl.vault.economy.EconomyResponse;
import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

/**
 * Handles the purchase flow for auction limit tier upgrades.
 * Follows transaction safety pattern: validate before charge, refund on failure.
 */
public class AuctionLimitPurchaseHandler {

    private final ServerShop plugin;
    private final AuctionTierCalculator tierCalculator;

    public AuctionLimitPurchaseHandler(ServerShop plugin) {
        this.plugin = plugin;
        this.tierCalculator = new AuctionTierCalculator(plugin);
    }

    /**
     * Process an auction limit purchase for a player.
     *
     * @param player Player attempting to purchase
     * @return true if command was handled
     */
    public boolean purchase(Player player) {
        // Check if feature is enabled
        if (!plugin.getConfig().getBoolean("auction_limits.enabled", true)) {
            player.sendMessage(colorize(getMessage("auction-feature-disabled")));
            return true;
        }

        // OP/bypass 체크 — 무제한 유저는 구매 불필요
        if (tierCalculator.isUnlimited(player)) {
            player.sendMessage(colorize(getMessage("auction-op-unlimited")));
            return true;
        }

        // Get current tier
        int currentTier = tierCalculator.getCurrentLimit(player);

        // Check if at max tier
        if (tierCalculator.isAtMaxTier(player)) {
            player.sendMessage(colorize(getMessage("auction-max-reached")
                    .replace("%max_limit%", String.valueOf(tierCalculator.getMaxLimit()))));
            return true;
        }

        // Get next tier price
        Integer nextTierPrice = tierCalculator.getNextTierPrice(player);
        if (nextTierPrice == null) {
            player.sendMessage(colorize(getMessage("auction-no-price")));
            return true;
        }

        // Check balance
        Economy economy = ServerShop.getEconomy();
        double balance = economy.getBalance(player);

        if (balance < nextTierPrice) {
            player.sendMessage(colorize(getMessage("not-enough-money")
                    .replace("%price%", String.format("%.0f", (double) nextTierPrice))
                    .replace("%balance%", String.format("%.0f", balance))));
            return true;
        }

        // Withdraw money
        EconomyResponse response = economy.withdrawPlayer(player, nextTierPrice);

        if (!response.transactionSuccess()) {
            player.sendMessage(colorize("&c거래 실패: " + response.errorMessage));
            plugin.getLogger().severe("Vault withdrawal failed for " + player.getName() + ": " + response.errorMessage);
            return true;
        }

        // Grant permission via LuckPerms
        int nextTier = currentTier + plugin.getConfig().getInt("auction_limits.step", 1);
        String permission = tierCalculator.getTierPermission(nextTier);

        if (permission == null) {
            // Refund - no permission configured for this tier
            economy.depositPlayer(player, nextTierPrice);
            player.sendMessage(colorize("&c티어 권한 설정 오류! 돈이 반환되었습니다."));
            plugin.getLogger().severe("No permission configured for auction tier " + nextTier + "! Purchase cancelled.");
            return true;
        }

        LuckPermsIntegration luckPerms = plugin.getLuckPermsIntegration();
        if (!luckPerms.isAvailable()) {
            // Refund - LuckPerms not available
            economy.depositPlayer(player, nextTierPrice);
            player.sendMessage(colorize("&cLuckPerms 연동 오류! 돈이 반환되었습니다."));
            plugin.getLogger().severe("LuckPerms not available! Purchase cancelled.");
            return true;
        }

        boolean permissionGranted = luckPerms.grantPermission(player.getUniqueId(), permission);

        if (!permissionGranted) {
            // Refund - permission grant failed
            economy.depositPlayer(player, nextTierPrice);
            player.sendMessage(colorize("&c권한 부여 실패! 돈이 반환되었습니다."));
            plugin.getLogger().severe("Failed to grant auction permission to " + player.getName() + "! Purchase cancelled and refunded.");
            return true;
        }

        // Success!
        double newBalance = economy.getBalance(player);
        player.sendMessage(colorize(getMessage("auction-purchased")
                .replace("%current_tier%", String.valueOf(currentTier))
                .replace("%next_tier%", String.valueOf(nextTier))
                .replace("%balance%", String.format("%.0f", newBalance))));

        // Log to console
        plugin.getLogger().info(player.getName() + " purchased auction limit tier " + currentTier + "->" + nextTier +
            " for " + nextTierPrice + " (permission: " + permission + ")");

        ServerShop.depositToServerAccount(nextTierPrice,
            player.getName() + " bought auction limit " + currentTier + "->" + nextTier);

        return true;
    }

    /**
     * Show information about player's current auction limit tier.
     *
     * @param player Player to show info to
     * @return true (command handled)
     */
    public boolean showInfo(Player player) {
        return showInfo(player, null);
    }

    /**
     * Show information about a player's current auction limit tier.
     * If targetPlayerName is provided, shows info for that player (admin only).
     *
     * @param sender Command sender
     * @param targetPlayerName Optional player name to check (null = check self)
     * @return true (command handled)
     */
    public boolean showInfo(CommandSender sender, String targetPlayerName) {
        // Check if feature is enabled
        if (!plugin.getConfig().getBoolean("auction_limits.enabled", true)) {
            sender.sendMessage(colorize(getMessage("auction-feature-disabled")));
            return true;
        }

        Player targetPlayer;

        if (targetPlayerName == null) {
            if (!(sender instanceof Player)) {
                sender.sendMessage(colorize(getMessage("auction-console-error")));
                return true;
            }
            targetPlayer = (Player) sender;
        } else {
            targetPlayer = Bukkit.getPlayer(targetPlayerName);
            if (targetPlayer == null) {
                sender.sendMessage(colorize("&c플레이어 '" + targetPlayerName + "'을(를) 찾을 수 없습니다. (온라인 상태가 아닙니다)"));
                return true;
            }
        }

        int currentTier = tierCalculator.getCurrentLimit(targetPlayer);

        // OP/bypass 체크 — 무제한 유저 표시
        if (tierCalculator.isUnlimited(targetPlayer)) {
            if (targetPlayer.equals(sender)) {
                sender.sendMessage(colorize(getMessage("auction-op-unlimited")));
            } else {
                sender.sendMessage(colorize("&e" + targetPlayer.getName() + "의 경매 한도: &a무제한 &7(OP)"));
            }
            return true;
        }

        // Check if at max tier
        if (tierCalculator.isAtMaxTier(targetPlayer)) {
            if (targetPlayer.equals(sender)) {
                sender.sendMessage(colorize(getMessage("auction-max-reached")
                        .replace("%max_limit%", String.valueOf(tierCalculator.getMaxLimit()))));
            } else {
                sender.sendMessage(colorize("&e" + targetPlayer.getName() + "의 경매 한도: &a" + currentTier + "개 &7(최대)"));
            }
            return true;
        }

        // Get next tier price
        Integer nextTierPrice = tierCalculator.getNextTierPrice(targetPlayer);

        if (nextTierPrice == null) {
            if (targetPlayer.equals(sender)) {
                sender.sendMessage(colorize(getMessage("auction-current-limit")
                        .replace("%current_limit%", String.valueOf(currentTier))));
                sender.sendMessage(colorize("&c다음 티어 구매 불가능"));
            } else {
                sender.sendMessage(colorize("&e" + targetPlayer.getName() + "의 경매 한도: &a" + currentTier + "개 &7| &c다음 티어 구매 불가능"));
            }
        } else {
            if (targetPlayer.equals(sender)) {
                sender.sendMessage(colorize(getMessage("auction-current-limit")
                        .replace("%current_limit%", String.valueOf(currentTier))));
                sender.sendMessage(colorize("&e다음 티어 가격: &a" + String.format("%.0f", (double) nextTierPrice) + "원"));
            } else {
                sender.sendMessage(colorize("&e" + targetPlayer.getName() + "의 경매 한도: &a" + currentTier + "개 &7| &6다음 티어 가격: &e" +
                        String.format("%.0f", (double) nextTierPrice) + "원"));
            }
        }

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
