package com.nearoutpost.servershop;

import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;

import java.io.File;
import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Manages nickname change cooldowns with YAML file persistence.
 * Thread-safe implementation using ConcurrentHashMap and synchronized methods.
 */
public class NicknameCooldownManager {

    private final ServerShop plugin;
    private final File cooldownFile;
    private FileConfiguration cooldownConfig;
    private final ConcurrentHashMap<UUID, Long> cooldownCache;

    public NicknameCooldownManager(ServerShop plugin) {
        this.plugin = plugin;
        this.cooldownFile = new File(plugin.getDataFolder(), "nicknames.yml");
        this.cooldownCache = new ConcurrentHashMap<>();
        loadCooldowns();
    }

    /**
     * Load cooldown data from nicknames.yml file.
     * Creates file if it doesn't exist.
     */
    private void loadCooldowns() {
        if (!cooldownFile.exists()) {
            try {
                cooldownFile.getParentFile().mkdirs();
                cooldownFile.createNewFile();
                plugin.getLogger().info("Created nicknames.yml for cooldown storage");
            } catch (IOException e) {
                plugin.getLogger().severe("Failed to create nicknames.yml: " + e.getMessage());
                return;
            }
        }

        cooldownConfig = YamlConfiguration.loadConfiguration(cooldownFile);

        // Load cooldowns into cache
        if (cooldownConfig.contains("cooldowns")) {
            for (String uuidString : cooldownConfig.getConfigurationSection("cooldowns").getKeys(false)) {
                try {
                    UUID playerId = UUID.fromString(uuidString);
                    long expiryTime = cooldownConfig.getLong("cooldowns." + uuidString);

                    // Only cache if cooldown hasn't expired
                    if (expiryTime > System.currentTimeMillis()) {
                        cooldownCache.put(playerId, expiryTime);
                    }
                } catch (IllegalArgumentException e) {
                    plugin.getLogger().warning("Invalid UUID in nicknames.yml: " + uuidString);
                }
            }
        }

        plugin.getLogger().info("Loaded " + cooldownCache.size() + " active nickname cooldowns");
    }

    /**
     * Check if a player is currently on cooldown.
     *
     * @param playerId Player's UUID
     * @return true if player is on cooldown, false otherwise
     */
    public synchronized boolean isOnCooldown(UUID playerId) {
        Long expiryTime = cooldownCache.get(playerId);
        if (expiryTime == null) {
            return false;
        }

        // Check if cooldown has expired
        if (expiryTime <= System.currentTimeMillis()) {
            cooldownCache.remove(playerId);
            return false;
        }

        return true;
    }

    /**
     * Get remaining cooldown time in milliseconds.
     *
     * @param playerId Player's UUID
     * @return Remaining milliseconds, or 0 if no cooldown
     */
    public synchronized long getRemainingCooldown(UUID playerId) {
        Long expiryTime = cooldownCache.get(playerId);
        if (expiryTime == null) {
            return 0;
        }

        long remaining = expiryTime - System.currentTimeMillis();
        if (remaining <= 0) {
            cooldownCache.remove(playerId);
            return 0;
        }

        return remaining;
    }

    /**
     * Set a cooldown for a player after a nickname purchase.
     * Persists to file immediately.
     *
     * @param playerId Player's UUID
     * @param durationMillis Cooldown duration in milliseconds
     */
    public synchronized void setCooldown(UUID playerId, long durationMillis) {
        long expiryTime = System.currentTimeMillis() + durationMillis;
        cooldownCache.put(playerId, expiryTime);

        // Persist to file
        cooldownConfig.set("cooldowns." + playerId.toString(), expiryTime);
        saveCooldowns();
    }

    /**
     * Remove a player's cooldown (admin command).
     *
     * @param playerId Player's UUID
     */
    public synchronized void removeCooldown(UUID playerId) {
        cooldownCache.remove(playerId);
        cooldownConfig.set("cooldowns." + playerId.toString(), null);
        saveCooldowns();
    }

    /**
     * Save cooldown data to nicknames.yml file synchronously.
     */
    private void saveCooldowns() {
        try {
            cooldownConfig.save(cooldownFile);
        } catch (IOException e) {
            plugin.getLogger().severe("Failed to save nicknames.yml: " + e.getMessage());
        }
    }

    /**
     * Parse duration string (e.g., "7d", "12h", "30m") to milliseconds.
     * Supports combinations like "1d12h30m" and plain numbers (interpreted as seconds).
     *
     * @param duration Duration string
     * @return Duration in milliseconds
     * @throws IllegalArgumentException if format is invalid
     */
    public static long parseDuration(String duration) throws IllegalArgumentException {
        if (duration == null || duration.trim().isEmpty()) {
            throw new IllegalArgumentException("Duration cannot be empty");
        }

        duration = duration.trim().toLowerCase();

        // Try parsing as plain number (seconds)
        try {
            long seconds = Long.parseLong(duration);
            return TimeUnit.SECONDS.toMillis(seconds);
        } catch (NumberFormatException e) {
            // Not a plain number, continue to pattern matching
        }

        // Pattern: allows combinations like "7d12h30m" or single units "7d"
        Pattern pattern = Pattern.compile("(\\d+)([dhms])");
        Matcher matcher = pattern.matcher(duration);

        long totalMillis = 0;
        boolean foundMatch = false;

        while (matcher.find()) {
            foundMatch = true;
            long value = Long.parseLong(matcher.group(1));
            String unit = matcher.group(2);

            switch (unit) {
                case "d":
                    totalMillis += TimeUnit.DAYS.toMillis(value);
                    break;
                case "h":
                    totalMillis += TimeUnit.HOURS.toMillis(value);
                    break;
                case "m":
                    totalMillis += TimeUnit.MINUTES.toMillis(value);
                    break;
                case "s":
                    totalMillis += TimeUnit.SECONDS.toMillis(value);
                    break;
            }
        }

        if (!foundMatch) {
            throw new IllegalArgumentException("Invalid duration format: " + duration +
                " (expected format: '7d', '12h', '30m', '1d12h30m', or seconds)");
        }

        return totalMillis;
    }

    /**
     * Format milliseconds to human-readable duration (e.g., "6d 23h 45m").
     * Omits zero values and seconds for brevity.
     *
     * @param millis Duration in milliseconds
     * @return Formatted string
     */
    public static String formatDuration(long millis) {
        if (millis <= 0) {
            return "0m";
        }

        long days = TimeUnit.MILLISECONDS.toDays(millis);
        millis -= TimeUnit.DAYS.toMillis(days);

        long hours = TimeUnit.MILLISECONDS.toHours(millis);
        millis -= TimeUnit.HOURS.toMillis(hours);

        long minutes = TimeUnit.MILLISECONDS.toMinutes(millis);

        StringBuilder sb = new StringBuilder();

        if (days > 0) {
            sb.append(days).append("d ");
        }
        if (hours > 0) {
            sb.append(hours).append("h ");
        }
        if (minutes > 0 || sb.length() == 0) {
            sb.append(minutes).append("m");
        }

        return sb.toString().trim();
    }

    /**
     * Reload cooldown data from file.
     * Used when config is reloaded.
     */
    public void reload() {
        cooldownCache.clear();
        loadCooldowns();
    }
}
