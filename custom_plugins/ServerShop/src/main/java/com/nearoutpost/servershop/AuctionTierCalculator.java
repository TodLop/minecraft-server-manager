package com.nearoutpost.servershop;

import org.bukkit.configuration.ConfigurationSection;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

/**
 * Calculates player's current auction limit tier and validates tier progression.
 * Adapted from TierCalculator for the auction limit purchase system.
 */
public class AuctionTierCalculator {

    private final JavaPlugin plugin;

    public AuctionTierCalculator(JavaPlugin plugin) {
        this.plugin = plugin;
    }

    private int getStep() {
        return plugin.getConfig().getInt("auction_limits.step", 1);
    }

    /**
     * Check if a player has unlimited auction slots (OP or bypass permission).
     *
     * @param player Player to check
     * @return true if player has unlimited auctions
     */
    public boolean isUnlimited(Player player) {
        if (player.isOp()) {
            return true;
        }
        String bypassPermission = plugin.getConfig().getString(
            "auction_limits.bypass_permission", "servershop.auction.bypass");
        return player.hasPermission(bypassPermission);
    }

    /**
     * Get the player's current auction limit tier.
     * Scans tier_permissions from highest to lowest to find the highest tier the player has.
     *
     * @param player Player to check
     * @return Current tier number (e.g. 3-10)
     */
    public int getCurrentLimit(Player player) {
        ConfigurationSection config = plugin.getConfig().getConfigurationSection("auction_limits");
        if (config == null) {
            plugin.getLogger().warning("auction_limits config section not found!");
            return getDefaultLimit();
        }

        int maxLimit = config.getInt("max_limit", 10);
        int defaultLimit = config.getInt("default_limit", 3);

        // Find the highest tier by checking all configured tier permissions
        int highestTier = defaultLimit;

        for (int tier = maxLimit; tier >= defaultLimit; tier -= getStep()) {
            String permission = config.getString("tier_permissions." + tier);
            if (permission != null && player.hasPermission(permission)) {
                if (tier > highestTier) {
                    highestTier = tier;
                }
            }
        }

        return highestTier;
    }

    /**
     * Get the price for the next tier upgrade.
     * Returns null if next tier is not purchasable (no price set or already at max).
     *
     * @param player Player to check
     * @return Price for next tier, or null if cannot purchase
     */
    public Integer getNextTierPrice(Player player) {
        int currentTier = getCurrentLimit(player);
        int maxLimit = plugin.getConfig().getInt("auction_limits.max_limit", 10);

        // Already at max tier
        if (currentTier >= maxLimit) {
            return null;
        }

        int nextTier = currentTier + getStep();

        // Check if price exists for next tier
        ConfigurationSection prices = plugin.getConfig().getConfigurationSection("auction_limits.tier_prices");
        if (prices == null || !prices.contains(String.valueOf(nextTier))) {
            return null;
        }

        if (prices.isInt(String.valueOf(nextTier)) || prices.isDouble(String.valueOf(nextTier))) {
            return prices.getInt(String.valueOf(nextTier));
        }

        return null;
    }

    /**
     * Get the permission node for a specific tier.
     *
     * @param tier Tier number
     * @return Permission node, or null if not configured
     */
    public String getTierPermission(int tier) {
        return plugin.getConfig().getString("auction_limits.tier_permissions." + tier);
    }

    /**
     * Get the default auction limit for all players.
     *
     * @return Default limit count
     */
    public int getDefaultLimit() {
        return plugin.getConfig().getInt("auction_limits.default_limit", 3);
    }

    /**
     * Get the maximum auction limit a player can purchase.
     *
     * @return Max limit count
     */
    public int getMaxLimit() {
        return plugin.getConfig().getInt("auction_limits.max_limit", 10);
    }

    /**
     * Check if a player is at maximum tier.
     *
     * @param player Player to check
     * @return true if at max tier
     */
    public boolean isAtMaxTier(Player player) {
        return isUnlimited(player) || getCurrentLimit(player) >= getMaxLimit();
    }
}
