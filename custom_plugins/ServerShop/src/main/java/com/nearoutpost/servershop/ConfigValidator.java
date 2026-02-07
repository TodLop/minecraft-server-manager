package com.nearoutpost.servershop;

import org.bukkit.configuration.ConfigurationSection;
import org.bukkit.plugin.java.JavaPlugin;

import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

/**
 * Validates ServerShop configuration structure and values.
 */
public class ConfigValidator {

    private final JavaPlugin plugin;

    public ConfigValidator(JavaPlugin plugin) {
        this.plugin = plugin;
    }

    /**
     * Validate the entire config structure.
     * Throws ConfigException if validation fails.
     *
     * @throws ConfigException if config is invalid
     */
    public void validate() throws ConfigException {
        validateSethomeSlots();
        validateNicknameShop();
        validateAuctionLimits();
    }

    /**
     * Validate the sethome_slots configuration section.
     *
     * @throws ConfigException if sethome_slots config is invalid
     */
    private void validateSethomeSlots() throws ConfigException {
        ConfigurationSection sethomeConfig = plugin.getConfig().getConfigurationSection("sethome_slots");

        if (sethomeConfig == null) {
            throw new ConfigException("Missing 'sethome_slots' configuration section");
        }

        // Validate default_homes
        if (!sethomeConfig.contains("default_homes")) {
            throw new ConfigException("Missing 'sethome_slots.default_homes'");
        }

        int defaultHomes = sethomeConfig.getInt("default_homes", -1);
        if (defaultHomes < 1 || defaultHomes > 100) {
            throw new ConfigException("'sethome_slots.default_homes' must be between 1 and 100 (got: " + defaultHomes + ")");
        }

        // Validate max_homes
        if (!sethomeConfig.contains("max_homes")) {
            throw new ConfigException("Missing 'sethome_slots.max_homes'");
        }

        int maxHomes = sethomeConfig.getInt("max_homes", -1);
        if (maxHomes < 1 || maxHomes > 100) {
            throw new ConfigException("'sethome_slots.max_homes' must be between 1 and 100 (got: " + maxHomes + ")");
        }

        if (maxHomes <= defaultHomes) {
            throw new ConfigException("'sethome_slots.max_homes' (" + maxHomes + ") must be greater than 'default_homes' (" + defaultHomes + ")");
        }

        // Validate tier_prices section exists
        ConfigurationSection tierPrices = sethomeConfig.getConfigurationSection("tier_prices");
        if (tierPrices == null) {
            throw new ConfigException("Missing 'sethome_slots.tier_prices' section");
        }

        // Validate tier_permissions section exists
        ConfigurationSection tierPermissions = sethomeConfig.getConfigurationSection("tier_permissions");
        if (tierPermissions == null) {
            throw new ConfigException("Missing 'sethome_slots.tier_permissions' section");
        }

        // Validate that all tiers have permission mappings
        for (int tier = defaultHomes; tier <= maxHomes; tier++) {
            String permission = tierPermissions.getString(String.valueOf(tier));
            if (permission == null || permission.isEmpty()) {
                throw new ConfigException("Missing permission mapping for tier " + tier + " in 'sethome_slots.tier_permissions'");
            }
        }

        // Validate purchasable tiers have valid prices (can be null for unpurchasable tiers)
        for (int tier = defaultHomes + 1; tier <= maxHomes; tier++) {
            if (tierPrices.contains(String.valueOf(tier))) {
                if (tierPrices.isInt(String.valueOf(tier)) || tierPrices.isDouble(String.valueOf(tier))) {
                    double price = tierPrices.getDouble(String.valueOf(tier));
                    if (price < 0) {
                        throw new ConfigException("Tier " + tier + " price cannot be negative (got: " + price + ")");
                    }
                }
                // If it's null or not a number, that's okay - means tier is not purchasable yet
            }
        }

        plugin.getLogger().info("Config validation passed: sethome_slots configuration is valid");
    }

    /**
     * Validate the nickname_shop configuration section.
     *
     * @throws ConfigException if nickname_shop config is invalid
     */
    private void validateNicknameShop() throws ConfigException {
        ConfigurationSection config = plugin.getConfig().getConfigurationSection("nickname_shop");

        if (config == null) {
            plugin.getLogger().warning("Missing 'nickname_shop' - feature disabled");
            return;
        }

        if (!config.getBoolean("enabled", true)) {
            plugin.getLogger().info("Nickname shop disabled in config");
            return;
        }

        // Validate price
        if (!config.contains("price")) {
            throw new ConfigException("Missing 'nickname_shop.price'");
        }
        double price = config.getDouble("price", -1);
        if (price < 0) {
            throw new ConfigException("'nickname_shop.price' cannot be negative");
        }

        // Validate cooldown
        if (!config.contains("cooldown")) {
            throw new ConfigException("Missing 'nickname_shop.cooldown'");
        }
        try {
            NicknameCooldownManager.parseDuration(config.getString("cooldown"));
        } catch (Exception e) {
            throw new ConfigException("Invalid cooldown format: " + e.getMessage());
        }

        // Validate lengths
        int minLength = config.getInt("min_length", 3);
        int maxLength = config.getInt("max_length", 16);
        if (minLength < 1 || maxLength > 32 || maxLength < minLength) {
            throw new ConfigException("Invalid length constraints (min: " + minLength + ", max: " + maxLength + ")");
        }

        // Validate regex pattern
        String pattern = config.getString("allowed_pattern");
        if (pattern != null && !pattern.trim().isEmpty()) {
            try {
                Pattern.compile(pattern);
            } catch (PatternSyntaxException e) {
                throw new ConfigException("Invalid regex pattern: " + e.getMessage());
            }
        }

        plugin.getLogger().info("Config validation passed: nickname_shop valid");
    }

    /**
     * Validate the auction_limits configuration section.
     *
     * @throws ConfigException if auction_limits config is invalid
     */
    private void validateAuctionLimits() throws ConfigException {
        ConfigurationSection config = plugin.getConfig().getConfigurationSection("auction_limits");

        if (config == null) {
            plugin.getLogger().warning("Missing 'auction_limits' - feature disabled");
            return;
        }

        if (!config.getBoolean("enabled", true)) {
            plugin.getLogger().info("Auction limits disabled in config");
            return;
        }

        // Validate default_limit
        int defaultLimit = config.getInt("default_limit", -1);
        if (defaultLimit < 1 || defaultLimit > 100) {
            throw new ConfigException("'auction_limits.default_limit' must be between 1 and 100 (got: " + defaultLimit + ")");
        }

        // Validate max_limit
        int maxLimit = config.getInt("max_limit", -1);
        if (maxLimit < 1 || maxLimit > 100) {
            throw new ConfigException("'auction_limits.max_limit' must be between 1 and 100 (got: " + maxLimit + ")");
        }

        if (maxLimit <= defaultLimit) {
            throw new ConfigException("'auction_limits.max_limit' (" + maxLimit + ") must be greater than 'default_limit' (" + defaultLimit + ")");
        }

        // Validate step
        int step = config.getInt("step", 1);
        if (step < 1 || step > 100) {
            throw new ConfigException("'auction_limits.step' must be between 1 and 100 (got: " + step + ")");
        }
        if ((maxLimit - defaultLimit) % step != 0) {
            throw new ConfigException("(max_limit - default_limit) must be divisible by step");
        }

        // Validate tier_prices section exists
        ConfigurationSection tierPrices = config.getConfigurationSection("tier_prices");
        if (tierPrices == null) {
            throw new ConfigException("Missing 'auction_limits.tier_prices' section");
        }

        // Validate tier_permissions section exists
        ConfigurationSection tierPermissions = config.getConfigurationSection("tier_permissions");
        if (tierPermissions == null) {
            throw new ConfigException("Missing 'auction_limits.tier_permissions' section");
        }

        // Validate that all tiers have permission mappings
        for (int tier = defaultLimit; tier <= maxLimit; tier += step) {
            String permission = tierPermissions.getString(String.valueOf(tier));
            if (permission == null || permission.isEmpty()) {
                throw new ConfigException("Missing permission mapping for tier " + tier + " in 'auction_limits.tier_permissions'");
            }
        }

        // Validate purchasable tiers have valid prices
        for (int tier = defaultLimit + step; tier <= maxLimit; tier += step) {
            if (tierPrices.contains(String.valueOf(tier))) {
                if (tierPrices.isInt(String.valueOf(tier)) || tierPrices.isDouble(String.valueOf(tier))) {
                    double price = tierPrices.getDouble(String.valueOf(tier));
                    if (price < 0) {
                        throw new ConfigException("Auction tier " + tier + " price cannot be negative (got: " + price + ")");
                    }
                }
            }
        }

        plugin.getLogger().info("Config validation passed: auction_limits configuration is valid");
    }

    /**
     * Exception thrown when config validation fails.
     */
    public static class ConfigException extends Exception {
        public ConfigException(String message) {
            super(message);
        }
    }
}
