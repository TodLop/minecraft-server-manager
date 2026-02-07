package dev.hjjang.moneyhistory.command;

import dev.hjjang.moneyhistory.MoneyHistoryPlugin;
import dev.hjjang.moneyhistory.config.ConfigManager;
import dev.hjjang.moneyhistory.database.DatabaseManager;
import dev.hjjang.moneyhistory.format.ConsoleFormatter;
import dev.hjjang.moneyhistory.format.PlayerFormatter;
import dev.hjjang.moneyhistory.model.HistoryEntry;
import dev.hjjang.moneyhistory.query.HistoryFilters;
import dev.hjjang.moneyhistory.query.HistoryQueryService;
import dev.hjjang.moneyhistory.util.FilterParser;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.OfflinePlayer;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

public class MoneyHistoryCommand implements CommandExecutor, TabCompleter {
    private final MoneyHistoryPlugin plugin;
    private final HistoryQueryService queryService;
    private final ConfigManager configManager;
    private final DatabaseManager databaseManager;

    public MoneyHistoryCommand(MoneyHistoryPlugin plugin, HistoryQueryService queryService,
                              ConfigManager configManager, DatabaseManager databaseManager) {
        this.plugin = plugin;
        this.queryService = queryService;
        this.configManager = configManager;
        this.databaseManager = databaseManager;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        // Handle sub-commands
        if (args.length > 0) {
            String subCommand = args[0].toLowerCase();

            switch (subCommand) {
                case "reload":
                    return handleReload(sender);

                case "cleanup":
                    if (args.length < 2) {
                        sendMessage(sender, Component.text("Usage: /mh cleanup <days>", NamedTextColor.RED));
                        return true;
                    }
                    return handleCleanup(sender, args[1]);

                case "stats":
                    String targetPlayer = args.length > 1 ? args[1] : null;
                    return handleStats(sender, targetPlayer);
            }
        }

        // Handle history viewing
        return handleView(sender, args);
    }

    private boolean handleView(CommandSender sender, String[] args) {
        // Parse arguments
        String targetPlayerName = null;
        int page = 1;
        UUID targetUuid = null;

        // Filter out filter arguments to find player name and page
        List<String> nonFilterArgs = new ArrayList<>();
        for (String arg : args) {
            if (!arg.startsWith("--")) {
                nonFilterArgs.add(arg);
            }
        }

        // Determine target player
        if (nonFilterArgs.isEmpty()) {
            // No args - view own history (players only)
            if (!(sender instanceof Player)) {
                sendMessage(sender, Component.text("Console must specify a player name.", NamedTextColor.RED));
                return true;
            }
            Player player = (Player) sender;
            targetUuid = player.getUniqueId();
            targetPlayerName = player.getName();
        } else if (nonFilterArgs.size() == 1) {
            // One arg - could be page number or player name
            try {
                page = Integer.parseInt(nonFilterArgs.get(0));
                // It's a page number, use sender as target
                if (!(sender instanceof Player)) {
                    sendMessage(sender, Component.text("Console must specify a player name.", NamedTextColor.RED));
                    return true;
                }
                Player player = (Player) sender;
                targetUuid = player.getUniqueId();
                targetPlayerName = player.getName();
            } catch (NumberFormatException e) {
                // It's a player name
                targetPlayerName = nonFilterArgs.get(0);
            }
        } else {
            // Two args - player name and page
            targetPlayerName = nonFilterArgs.get(0);
            try {
                page = Integer.parseInt(nonFilterArgs.get(1));
            } catch (NumberFormatException e) {
                sendMessage(sender, Component.text("Invalid page number: " + nonFilterArgs.get(1), NamedTextColor.RED));
                return true;
            }
        }

        // If we don't have UUID yet, look up player
        if (targetUuid == null) {
            OfflinePlayer offlinePlayer = Bukkit.getOfflinePlayerIfCached(targetPlayerName);
            if (offlinePlayer == null || !offlinePlayer.hasPlayedBefore()) {
                sendMessage(sender, Component.text("Player not found: " + targetPlayerName, NamedTextColor.RED));
                return true;
            }
            targetUuid = offlinePlayer.getUniqueId();
            targetPlayerName = offlinePlayer.getName();
        }

        // Check permissions
        if (sender instanceof Player) {
            Player player = (Player) sender;
            if (!player.getUniqueId().equals(targetUuid) && !player.hasPermission("moneyhistory.view.others")) {
                sendMessage(sender, Component.text("You don't have permission to view other players' history.", NamedTextColor.RED));
                return true;
            }
        }

        // Parse filters
        HistoryFilters filters = FilterParser.parseFilters(args);

        // Validate page
        if (page < 1) {
            page = 1;
        }
        int maxPages = configManager.getMaxPages();
        if (page > maxPages) {
            sendMessage(sender, Component.text("Page number exceeds maximum (" + maxPages + ")", NamedTextColor.RED));
            return true;
        }

        // Get current balance from Vault
        OfflinePlayer targetOfflinePlayer = Bukkit.getOfflinePlayer(targetUuid);
        double currentBalance = plugin.getVaultIntegration().getEconomy().getBalance(targetOfflinePlayer);

        // Query history asynchronously
        final UUID finalTargetUuid = targetUuid;
        final String finalTargetName = targetPlayerName;
        final int finalPage = page;

        queryService.getHistory(finalTargetUuid, finalPage, filters).thenAccept(entries -> {
            queryService.getHistoryCount(finalTargetUuid, filters).thenAccept(totalEntries -> {
                int entriesPerPage = configManager.getEntriesPerPage();
                int totalPages = (int) Math.ceil((double) totalEntries / entriesPerPage);

                // Format and send output
                if (sender instanceof Player) {
                    List<Component> lines = PlayerFormatter.formatHistory(
                            finalTargetName, entries, finalPage, totalPages, totalEntries,
                            currentBalance, configManager.isUseRelativeTime(), configManager.isShowUnknownHelp()
                    );
                    for (Component line : lines) {
                        sendMessage(sender, line);
                    }
                } else {
                    List<String> lines = ConsoleFormatter.formatHistory(
                            finalTargetName, entries, finalPage, totalPages, totalEntries, currentBalance
                    );
                    for (String line : lines) {
                        sender.sendMessage(line);
                    }
                }
            });
        }).exceptionally(ex -> {
            sendMessage(sender, Component.text("Failed to query history: " + ex.getMessage(), NamedTextColor.RED));
            plugin.getLogger().log(java.util.logging.Level.SEVERE, "Stack trace:", ex);
            return null;
        });

        return true;
    }

    private boolean handleReload(CommandSender sender) {
        if (!sender.hasPermission("moneyhistory.reload")) {
            sendMessage(sender, Component.text("You don't have permission to reload the configuration.", NamedTextColor.RED));
            return true;
        }

        configManager.reload();
        queryService.clearCache();

        sendMessage(sender, Component.text("Configuration reloaded successfully.", NamedTextColor.GREEN));
        return true;
    }

    private boolean handleCleanup(CommandSender sender, String daysStr) {
        if (!sender.hasPermission("moneyhistory.cleanup")) {
            sendMessage(sender, Component.text("You don't have permission to clean up records.", NamedTextColor.RED));
            return true;
        }

        int days;
        try {
            days = Integer.parseInt(daysStr);
        } catch (NumberFormatException e) {
            sendMessage(sender, Component.text("Invalid number of days: " + daysStr, NamedTextColor.RED));
            return true;
        }

        if (days < 1) {
            sendMessage(sender, Component.text("Days must be at least 1.", NamedTextColor.RED));
            return true;
        }

        sendMessage(sender, Component.text("Starting cleanup of records older than " + days + " days...", NamedTextColor.YELLOW));

        // Execute cleanup asynchronously
        CleanupService cleanupService = new CleanupService(plugin, databaseManager);
        cleanupService.cleanup(days).thenAccept(deletedCount -> {
            sendMessage(sender, Component.text("Cleanup completed. Deleted " + deletedCount + " records.", NamedTextColor.GREEN));
        }).exceptionally(ex -> {
            sendMessage(sender, Component.text("Cleanup failed: " + ex.getMessage(), NamedTextColor.RED));
            plugin.getLogger().log(java.util.logging.Level.SEVERE, "Stack trace:", ex);
            return null;
        });

        return true;
    }

    private boolean handleStats(CommandSender sender, String targetPlayer) {
        if (!sender.hasPermission("moneyhistory.stats")) {
            sendMessage(sender, Component.text("You don't have permission to view statistics.", NamedTextColor.RED));
            return true;
        }

        sendMessage(sender, Component.text("Statistics feature not yet implemented.", NamedTextColor.YELLOW));
        return true;
    }

    private void sendMessage(CommandSender sender, Component message) {
        if (sender instanceof Player) {
            sender.sendMessage(message);
        } else {
            sender.sendMessage(net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer.plainText().serialize(message));
        }
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        List<String> completions = new ArrayList<>();

        if (args.length == 1) {
            // First argument - sub-commands or player names
            completions.add("reload");
            completions.add("cleanup");
            completions.add("stats");

            // Add online player names
            for (Player player : Bukkit.getOnlinePlayers()) {
                if (sender.hasPermission("moneyhistory.view.others") || sender.getName().equals(player.getName())) {
                    completions.add(player.getName());
                }
            }

            // Filter based on input
            return completions.stream()
                    .filter(s -> s.toLowerCase().startsWith(args[0].toLowerCase()))
                    .collect(Collectors.toList());
        }

        return completions;
    }
}
