package com.nearoutpost.servershop;

import net.luckperms.api.LuckPerms;
import net.luckperms.api.model.user.User;
import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.command.CommandSender;
import org.bukkit.configuration.ConfigurationSection;

import java.util.*;
import java.util.concurrent.CompletableFuture;

/**
 * Manages leaderboards for sethome and auction systems.
 * Queries ALL players from LuckPerms asynchronously, sorts by tier, and paginates results.
 */
public class LeaderboardManager {

    private static final int ENTRIES_PER_PAGE = 10;

    private final ServerShop plugin;

    public LeaderboardManager(ServerShop plugin) {
        this.plugin = plugin;
    }

    /**
     * Show sethome slot leaderboard (admin only).
     * Queries all players from LuckPerms async.
     *
     * @param sender Command sender to display results to
     * @param page Page number (1-based)
     */
    public void showSethomeLeaderboard(CommandSender sender, int page) {
        LuckPermsIntegration luckPermsIntegration = plugin.getLuckPermsIntegration();
        if (!luckPermsIntegration.isAvailable()) {
            sender.sendMessage(colorize("&cLuckPerms를 사용할 수 없습니다."));
            return;
        }

        LuckPerms luckPerms = luckPermsIntegration.getApi();

        // Run async to avoid blocking the main thread
        luckPerms.getUserManager().getUniqueUsers().thenAcceptAsync(uuids -> {
            ConfigurationSection config = plugin.getConfig().getConfigurationSection("sethome_slots");
            if (config == null) {
                sendOnMainThread(sender, colorize("&csethome_slots 설정을 찾을 수 없습니다."));
                return;
            }

            int maxHomes = config.getInt("max_homes", 10);
            int defaultHomes = config.getInt("default_homes", 3);

            List<PlayerTierEntry> entries = new ArrayList<>();

            for (UUID uuid : uuids) {
                try {
                    User user = luckPerms.getUserManager().loadUser(uuid).join();
                    if (user == null) continue;

                    int highestTier = defaultHomes;

                    // Check configured tier permissions
                    for (int tier = maxHomes; tier >= defaultHomes; tier--) {
                        String permission = config.getString("tier_permissions." + tier);
                        if (permission != null && user.getCachedData().getPermissionData().checkPermission(permission).asBoolean()) {
                            if (tier > highestTier) {
                                highestTier = tier;
                            }
                        }
                    }

                    // Only include players above default tier
                    if (highestTier > defaultHomes) {
                        String name = user.getUsername();
                        if (name == null) name = uuid.toString().substring(0, 8);
                        entries.add(new PlayerTierEntry(name, highestTier));
                    }
                } catch (Exception e) {
                    // Skip players that fail to load
                }
            }

            // Sort by tier descending
            entries.sort((a, b) -> Integer.compare(b.tier, a.tier));

            // Paginate and display on main thread
            sendOnMainThread(sender, formatLeaderboard(entries, page, "홈 슬롯 순위", "개", "severshop sethome top"));
        }).exceptionally(ex -> {
            sendOnMainThread(sender, colorize("&c리더보드 조회 중 오류가 발생했습니다."));
            plugin.getLogger().severe("Failed to fetch sethome leaderboard: " + ex.getMessage());
            return null;
        });
    }

    /**
     * Show auction limit leaderboard (admin only).
     * Queries all players from LuckPerms async.
     *
     * @param sender Command sender to display results to
     * @param page Page number (1-based)
     */
    public void showAuctionLeaderboard(CommandSender sender, int page) {
        LuckPermsIntegration luckPermsIntegration = plugin.getLuckPermsIntegration();
        if (!luckPermsIntegration.isAvailable()) {
            sender.sendMessage(colorize("&cLuckPerms를 사용할 수 없습니다."));
            return;
        }

        LuckPerms luckPerms = luckPermsIntegration.getApi();

        luckPerms.getUserManager().getUniqueUsers().thenAcceptAsync(uuids -> {
            ConfigurationSection config = plugin.getConfig().getConfigurationSection("auction_limits");
            if (config == null) {
                sendOnMainThread(sender, colorize("&cauction_limits 설정을 찾을 수 없습니다."));
                return;
            }

            int maxLimit = config.getInt("max_limit", 10);
            int defaultLimit = config.getInt("default_limit", 3);

            List<PlayerTierEntry> entries = new ArrayList<>();

            for (UUID uuid : uuids) {
                try {
                    User user = luckPerms.getUserManager().loadUser(uuid).join();
                    if (user == null) continue;

                    int highestTier = defaultLimit;

                    int step = config.getInt("step", 1);
            for (int tier = maxLimit; tier >= defaultLimit; tier -= step) {
                        String permission = config.getString("tier_permissions." + tier);
                        if (permission != null && user.getCachedData().getPermissionData().checkPermission(permission).asBoolean()) {
                            if (tier > highestTier) {
                                highestTier = tier;
                            }
                        }
                    }

                    // Only include players above default tier
                    if (highestTier > defaultLimit) {
                        String name = user.getUsername();
                        if (name == null) name = uuid.toString().substring(0, 8);
                        entries.add(new PlayerTierEntry(name, highestTier));
                    }
                } catch (Exception e) {
                    // Skip players that fail to load
                }
            }

            entries.sort((a, b) -> Integer.compare(b.tier, a.tier));

            sendOnMainThread(sender, formatLeaderboard(entries, page, "경매 한도 순위", "개", "severshop auction top"));
        }).exceptionally(ex -> {
            sendOnMainThread(sender, colorize("&c리더보드 조회 중 오류가 발생했습니다."));
            plugin.getLogger().severe("Failed to fetch auction leaderboard: " + ex.getMessage());
            return null;
        });
    }

    /**
     * Format leaderboard entries into paginated display strings.
     */
    private String formatLeaderboard(List<PlayerTierEntry> entries, int page, String title, String unit, String nextCommand) {
        if (entries.isEmpty()) {
            return colorize("&7구매 기록이 있는 플레이어가 없습니다.");
        }

        int totalPages = (int) Math.ceil((double) entries.size() / ENTRIES_PER_PAGE);
        if (page < 1) page = 1;
        if (page > totalPages) page = totalPages;

        int startIndex = (page - 1) * ENTRIES_PER_PAGE;
        int endIndex = Math.min(startIndex + ENTRIES_PER_PAGE, entries.size());

        StringBuilder sb = new StringBuilder();
        sb.append(colorize("&6=== " + title + " (" + page + "/" + totalPages + " 페이지) ===\n"));

        for (int i = startIndex; i < endIndex; i++) {
            PlayerTierEntry entry = entries.get(i);
            sb.append(colorize("&e#" + (i + 1) + " &f" + entry.name + " &7— &a" + entry.tier + unit + "\n"));
        }

        if (page < totalPages) {
            sb.append(colorize("&7다음 페이지: &f/" + nextCommand + " " + (page + 1)));
        }

        return sb.toString().stripTrailing();
    }

    /**
     * Send a message to a CommandSender on the main Bukkit thread.
     */
    private void sendOnMainThread(CommandSender sender, String message) {
        Bukkit.getScheduler().runTask(plugin, () -> sender.sendMessage(message));
    }

    private String colorize(String message) {
        return ChatColor.translateAlternateColorCodes('&', message);
    }

    /**
     * Simple data holder for leaderboard entries.
     */
    private static class PlayerTierEntry {
        final String name;
        final int tier;

        PlayerTierEntry(String name, int tier) {
            this.name = name;
            this.tier = tier;
        }
    }
}
