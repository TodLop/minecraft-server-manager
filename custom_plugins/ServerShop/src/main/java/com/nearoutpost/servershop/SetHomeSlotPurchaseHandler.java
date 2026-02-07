package com.nearoutpost.servershop;

import net.milkbowl.vault.economy.Economy;
import net.milkbowl.vault.economy.EconomyResponse;
import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

/**
 * Handles the purchase flow for sethome slot upgrades.
 */
public class SetHomeSlotPurchaseHandler {

    private final ServerShop plugin;
    private final TierCalculator tierCalculator;

    public SetHomeSlotPurchaseHandler(ServerShop plugin) {
        this.plugin = plugin;
        this.tierCalculator = new TierCalculator(plugin);
    }

    /**
     * Process a sethome slot purchase for a player.
     *
     * @param player Player attempting to purchase
     * @return true if command was handled (doesn't mean purchase succeeded)
     */
    public boolean purchase(Player player) {
        // Check if player has unlimited homes
        if (tierCalculator.isUnlimited(player)) {
            player.sendMessage(colorize(getMessage("sethome-op-unlimited")));
            return true;
        }

        // Get current tier
        int currentTier = tierCalculator.getCurrentTier(player);

        // Check if at max tier
        if (tierCalculator.isAtMaxTier(player)) {
            player.sendMessage(colorize(getMessage("sethome-max-reached")
                    .replace("%max_homes%", String.valueOf(tierCalculator.getMaxHomes()))));
            return true;
        }

        // Get next tier price
        Integer nextTierPrice = tierCalculator.getNextTierPrice(player);
        if (nextTierPrice == null) {
            player.sendMessage(colorize(getMessage("sethome-no-price")));
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
        int nextTier = currentTier + 1;
        String permission = tierCalculator.getTierPermission(nextTier);

        if (permission == null) {
            // Refund - no permission configured for this tier
            economy.depositPlayer(player, nextTierPrice);
            player.sendMessage(colorize("&c티어 권한 설정 오류! 돈이 반환되었습니다."));
            plugin.getLogger().severe("No permission configured for tier " + nextTier + "! Purchase cancelled.");
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

        // Grant base permission first (required for multiple homes)
        boolean basePermGranted = luckPerms.grantPermission(player.getUniqueId(), "essentials.sethome.multiple");

        // Then grant tier-specific permission
        boolean permissionGranted = luckPerms.grantPermission(player.getUniqueId(), permission);

        // Check if both succeeded
        if (!basePermGranted || !permissionGranted) {
            // Refund - permission grant failed
            economy.depositPlayer(player, nextTierPrice);
            player.sendMessage(colorize("&c권한 부여 실패! 돈이 반환되었습니다."));
            plugin.getLogger().severe("Failed to grant permission to " + player.getName() + "! Purchase cancelled and refunded.");
            return true;
        }

        // Success!
        double newBalance = economy.getBalance(player);
        player.sendMessage(colorize(getMessage("sethome-purchased")
                .replace("%current_tier%", String.valueOf(currentTier))
                .replace("%next_tier%", String.valueOf(nextTier))
                .replace("%balance%", String.format("%.0f", newBalance))));

        // Log to console
        plugin.getLogger().info(player.getName() + " purchased sethome slot tier " + currentTier + "->" + nextTier +
            " for " + nextTierPrice + " (permissions: essentials.sethome.multiple, " + permission + ")");

        return true;
    }

    /**
     * Show information about player's current sethome tier.
     *
     * @param player Player to show info to
     * @return true (command handled)
     */
    public boolean showInfo(Player player) {
        return showInfo(player, null);
    }

    /**
     * Show information about a player's current sethome tier.
     * If targetPlayerName is provided, shows info for that player (OP only).
     *
     * @param sender Command sender (player requesting info)
     * @param targetPlayerName Optional player name to check (null = check self)
     * @return true (command handled)
     */
    public boolean showInfo(CommandSender sender, String targetPlayerName) {
        Player targetPlayer;

        // Determine target player
        if (targetPlayerName == null) {
            // Check self
            if (!(sender instanceof Player)) {
                sender.sendMessage(colorize("&c이 명령어는 플레이어만 사용할 수 있습니다."));
                return true;
            }
            targetPlayer = (Player) sender;
        } else {
            // Check another player (OP only)
            targetPlayer = Bukkit.getPlayer(targetPlayerName);
            if (targetPlayer == null) {
                sender.sendMessage(colorize("&c플레이어 '" + targetPlayerName + "'을(를) 찾을 수 없습니다. (온라인 상태가 아닙니다)"));
                return true;
            }
        }

        // Check if target player has unlimited homes
        if (tierCalculator.isUnlimited(targetPlayer)) {
            if (targetPlayer.equals(sender)) {
                sender.sendMessage(colorize(getMessage("sethome-op-unlimited")));
            } else {
                sender.sendMessage(colorize("&e" + targetPlayer.getName() + "의 홈 슬롯: &a무제한 &7(OP)"));
            }
            return true;
        }

        int currentTier = tierCalculator.getCurrentTier(targetPlayer);

        // Check if at max tier
        if (tierCalculator.isAtMaxTier(targetPlayer)) {
            if (targetPlayer.equals(sender)) {
                sender.sendMessage(colorize(getMessage("sethome-max-reached")
                        .replace("%max_homes%", String.valueOf(tierCalculator.getMaxHomes()))));
            } else {
                sender.sendMessage(colorize("&e" + targetPlayer.getName() + "의 홈 슬롯: &a" + currentTier + "개 &7(최대)"));
            }
            return true;
        }

        // Get next tier price
        Integer nextTierPrice = tierCalculator.getNextTierPrice(targetPlayer);

        if (nextTierPrice == null) {
            if (targetPlayer.equals(sender)) {
                sender.sendMessage(colorize("&e현재 홈 슬롯: &a" + currentTier + "개 &7| &c다음 티어 구매 불가능"));
            } else {
                sender.sendMessage(colorize("&e" + targetPlayer.getName() + "의 홈 슬롯: &a" + currentTier + "개 &7| &c다음 티어 구매 불가능"));
            }
        } else {
            if (targetPlayer.equals(sender)) {
                sender.sendMessage(colorize(getMessage("sethome-current-tier")
                        .replace("%current_tier%", String.valueOf(currentTier))
                        .replace("%next_price%", String.format("%.0f", (double) nextTierPrice))));
            } else {
                sender.sendMessage(colorize("&e" + targetPlayer.getName() + "의 홈 슬롯: &a" + currentTier + "개 &7| &6다음 티어 가격: &e" +
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
