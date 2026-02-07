package com.nearoutpost.servershop;

import org.bukkit.configuration.ConfigurationSection;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

/**
 * Calculates player's current sethome tier and validates tier progression.
 */
public class TierCalculator {

    private static final int UNLIMITED = -1;

    private final JavaPlugin plugin;

    public TierCalculator(JavaPlugin plugin) {
        this.plugin = plugin;
    }

    /**
     * Get the player's current sethome tier.
     * Returns UNLIMITED (-1) if player has OP or bypass permission.
     *
     * @param player Player to check
     * @return Current tier number (3-10), or UNLIMITED (-1)
     */
    public int getCurrentTier(Player player) {
        // Check for unlimited status first
        if (isUnlimited(player)) {
            return UNLIMITED;
        }

        ConfigurationSection config = plugin.getConfig().getConfigurationSection("sethome_slots");
        if (config == null) {
            plugin.getLogger().warning("sethome_slots config section not found!");
            return getDefaultHomes();
        }

        int maxHomes = config.getInt("max_homes", 10);
        int defaultHomes = config.getInt("default_homes", 3);

        // Find the highest tier by checking all configured tier permissions
        int highestTier = defaultHomes;

        // Check configured tier permissions (homes3, homes4, etc.)
        for (int tier = maxHomes; tier >= defaultHomes; tier--) {
            String permission = config.getString("tier_permissions." + tier);
            if (permission != null && player.hasPermission(permission)) {
                if (tier > highestTier) {
                    highestTier = tier;
                }
            }
        }

        // Check for legacy sethome permissions (vip, staff, etc.) for backward compatibility
        // Read from optional legacy_permissions config section
        org.bukkit.configuration.ConfigurationSection legacySection = config.getConfigurationSection("legacy_permissions");
        if (legacySection != null) {
            for (String key : legacySection.getKeys(false)) {
                int tierValue = legacySection.getInt(key);
                String permissionNode = "essentials.sethome.multiple." + key;
                if (player.hasPermission(permissionNode)) {
                    if (tierValue > highestTier) {
                        highestTier = tierValue;
                    }
                }
            }
        }

        return highestTier;
    }

    /**
     * Check if player has unlimited sethome slots.
     * True if player is OP or has bypass permission.
     *
     * @param player Player to check
     * @return true if player has unlimited homes
     */
    public boolean isUnlimited(Player player) {
        if (player.isOp()) {
            return true;
        }

        String bypassPermission = plugin.getConfig().getString("sethome_slots.bypass_permission", "servershop.sethome.bypass");
        return player.hasPermission(bypassPermission);
    }

    /**
     * Get the price for the next tier upgrade.
     * Returns null if next tier is not purchasable (no price set or already at max).
     *
     * @param player Player to check
     * @return Price for next tier, or null if cannot purchase
     */
    public Integer getNextTierPrice(Player player) {
        int currentTier = getCurrentTier(player);

        // Unlimited players cannot purchase
        if (currentTier == UNLIMITED) {
            return null;
        }

        int maxHomes = plugin.getConfig().getInt("sethome_slots.max_homes", 10);

        // Already at max tier
        if (currentTier >= maxHomes) {
            return null;
        }

        int nextTier = currentTier + 1;

        // Check if price exists for next tier
        ConfigurationSection prices = plugin.getConfig().getConfigurationSection("sethome_slots.tier_prices");
        if (prices == null || !prices.contains(String.valueOf(nextTier))) {
            return null;
        }

        // Get price (can be null if explicitly set to null)
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
        return plugin.getConfig().getString("sethome_slots.tier_permissions." + tier);
    }

    /**
     * Get the default number of homes for all players.
     *
     * @return Default homes count
     */
    public int getDefaultHomes() {
        return plugin.getConfig().getInt("sethome_slots.default_homes", 3);
    }

    /**
     * Get the maximum number of homes a player can purchase.
     *
     * @return Max homes count
     */
    public int getMaxHomes() {
        return plugin.getConfig().getInt("sethome_slots.max_homes", 10);
    }

    /**
     * Check if a player is at maximum tier.
     *
     * @param player Player to check
     * @return true if at max tier (but not unlimited)
     */
    public boolean isAtMaxTier(Player player) {
        int currentTier = getCurrentTier(player);
        return currentTier != UNLIMITED && currentTier >= getMaxHomes();
    }
}
