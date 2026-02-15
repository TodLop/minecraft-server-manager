package com.nearoutpost.servershop.commands;

import com.nearoutpost.servershop.ServerShop;
import com.nearoutpost.servershop.LeaderboardManager;
import net.milkbowl.vault.economy.Economy;
import net.milkbowl.vault.economy.EconomyResponse;
import org.bukkit.ChatColor;
import org.bukkit.Material;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.configuration.ConfigurationSection;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.stream.Collectors;

public class BuyCommand implements CommandExecutor, TabCompleter {

    private final ServerShop plugin;
    private final LeaderboardManager leaderboardManager;

    public BuyCommand(ServerShop plugin) {
        this.plugin = plugin;
        this.leaderboardManager = new LeaderboardManager(plugin);
        plugin.getCommand("severshop").setTabCompleter(this);
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        // No args → show help
        if (args.length < 1) {
            showHelp(sender);
            return true;
        }

        String sub = args[0].toLowerCase();

        // Reload subcommand for admins
        if (sub.equals("reload")) {
            if (sender.hasPermission("servershop.admin")) {
                try {
                    plugin.reloadConfig();
                    new com.nearoutpost.servershop.ConfigValidator(plugin).validate();
                    sender.sendMessage(colorize(getMessage("reload")));
                } catch (com.nearoutpost.servershop.ConfigValidator.ConfigException e) {
                    sender.sendMessage(colorize("&c설정 검증 실패: " + e.getMessage()));
                    plugin.getLogger().severe("Config validation failed after reload: " + e.getMessage());
                }
                return true;
            }
        }

        // Help subcommand
        if (sub.equals("help")) {
            showHelp(sender);
            return true;
        }

        // Sethome slot purchase routing
        if (sub.equals("sethome")) {
            return handleSethomeCommand(sender, args);
        }

        // Nickname change purchase routing
        if (sub.equals("nickname")) {
            return handleNicknameCommand(sender, args);
        }

        // Anvil access purchase routing
        if (sub.equals("anvil")) {
            return handleAnvilCommand(sender, args);
        }

        // Craft access purchase routing
        if (sub.equals("craft")) {
            return handleCraftCommand(sender, args);
        }

        // Auction limit purchase routing
        if (sub.equals("auction")) {
            return handleAuctionCommand(sender, args);
        }

        // Must be a player for item purchases
        if (!(sender instanceof Player)) {
            sender.sendMessage("This command can only be used by players.");
            return true;
        }

        Player player = (Player) sender;

        String itemName = args[0].toLowerCase();
        int amount = 1;

        // Parse amount
        if (args.length >= 2) {
            try {
                amount = Integer.parseInt(args[1]);
                if (amount < 1) {
                    player.sendMessage(colorize(getMessage("invalid-amount")));
                    return true;
                }
            } catch (NumberFormatException e) {
                player.sendMessage(colorize(getMessage("invalid-amount")));
                return true;
            }
        }

        // Check if item exists in Minecraft
        Material material = Material.matchMaterial(itemName);
        if (material == null) {
            player.sendMessage(colorize(getMessage("invalid-item").replace("%item%", itemName)));
            return true;
        }

        // Check if item is for sale
        ConfigurationSection prices = plugin.getConfig().getConfigurationSection("prices");
        if (prices == null || !prices.contains(itemName)) {
            player.sendMessage(colorize(getMessage("not-for-sale")));
            return true;
        }

        double pricePerItem = prices.getDouble(itemName);
        double totalPrice = pricePerItem * amount;

        // Check economy
        Economy economy = ServerShop.getEconomy();
        double balance = economy.getBalance(player);

        if (balance < totalPrice) {
            player.sendMessage(colorize(getMessage("not-enough-money")
                    .replace("%price%", String.format("%.0f", totalPrice))
                    .replace("%balance%", String.format("%.0f", balance))));
            return true;
        }

        // Check inventory space
        ItemStack itemStack = new ItemStack(material, amount);
        HashMap<Integer, ItemStack> leftover = player.getInventory().addItem(itemStack);

        if (!leftover.isEmpty()) {
            // Remove items that were added
            player.getInventory().removeItem(itemStack);
            // Return leftover
            for (ItemStack left : leftover.values()) {
                player.getInventory().addItem(left);
            }
            player.sendMessage(colorize(getMessage("inventory-full")));
            return true;
        }

        // Withdraw money
        EconomyResponse response = economy.withdrawPlayer(player, totalPrice);

        if (response.transactionSuccess()) {
            player.sendMessage(colorize(getMessage("bought")
                    .replace("%item%", material.name().toLowerCase().replace("_", " "))
                    .replace("%amount%", String.valueOf(amount))
                    .replace("%price%", String.format("%.0f", totalPrice))));
            ServerShop.depositToServerAccount(totalPrice,
                player.getName() + " bought " + material.name().toLowerCase() + " x" + amount);
        } else {
            // Refund items if transaction failed
            player.getInventory().removeItem(itemStack);
            player.sendMessage(colorize("&cTransaction failed: " + response.errorMessage));
        }

        return true;
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        List<String> completions = new ArrayList<>();

        if (args.length == 1) {
            String input = args[0].toLowerCase();

            // Special commands
            if ("sethome".startsWith(input)) completions.add("sethome");
            if ("nickname".startsWith(input)) completions.add("nickname");
            if ("anvil".startsWith(input)) completions.add("anvil");
            if ("craft".startsWith(input)) completions.add("craft");
            if ("auction".startsWith(input)) completions.add("auction");
            if ("help".startsWith(input)) completions.add("help");

            if (sender.hasPermission("servershop.admin") && "reload".startsWith(input)) {
                completions.add("reload");
            }

            // Item names from config
            ConfigurationSection prices = plugin.getConfig().getConfigurationSection("prices");
            if (prices != null) {
                completions.addAll(prices.getKeys(false).stream()
                        .filter(key -> key.toLowerCase().startsWith(input))
                        .collect(Collectors.toList()));
            }
        } else if (args.length == 2) {
            String sub = args[0].toLowerCase();
            String input = args[1].toLowerCase();

            if (sub.equals("sethome")) {
                if ("info".startsWith(input)) completions.add("info");
                if (sender.hasPermission("servershop.admin") && "top".startsWith(input)) {
                    completions.add("top");
                }
            } else if (sub.equals("nickname")) {
                if ("info".startsWith(input)) completions.add("info");
                if ("reset".startsWith(input)) completions.add("reset");
                if (sender.hasPermission("servershop.nickname.admin")) {
                    if ("set".startsWith(input)) completions.add("set");
                    if ("resetcooldown".startsWith(input)) completions.add("resetcooldown");
                }
            } else if (sub.equals("anvil")) {
                if ("info".startsWith(input)) completions.add("info");
            } else if (sub.equals("craft")) {
                if ("info".startsWith(input)) completions.add("info");
            } else if (sub.equals("auction")) {
                if ("info".startsWith(input)) completions.add("info");
                if (sender.hasPermission("servershop.admin") && "top".startsWith(input)) {
                    completions.add("top");
                }
            } else {
                // Suggest amounts for item purchases
                completions.add("1");
                completions.add("16");
                completions.add("32");
                completions.add("64");
            }
        } else if (args.length == 3) {
            String sub = args[0].toLowerCase();
            String action = args[1].toLowerCase();

            // /severshop sethome info <player> (admin)
            if (sub.equals("sethome") && action.equals("info") && sender.isOp()) {
                return getOnlinePlayerNames(args[2]);
            }

            // /severshop nickname set|resetcooldown|reset <player> (admin)
            if (sub.equals("nickname") && (action.equals("set") || action.equals("resetcooldown") || action.equals("reset"))
                    && sender.hasPermission("servershop.nickname.admin")) {
                return getOnlinePlayerNames(args[2]);
            }

            // /severshop auction info <player> (admin)
            if (sub.equals("auction") && action.equals("info") && sender.hasPermission("servershop.admin")) {
                return getOnlinePlayerNames(args[2]);
            }
        }

        return completions;
    }

    /**
     * Show help listing all available commands.
     */
    private void showHelp(CommandSender sender) {
        StringBuilder sb = new StringBuilder();
        sb.append(colorize("&6=== 서버상점 도움말 ===\n"));
        sb.append(colorize("&6/severshop <아이템> [수량] &7- 아이템 구매\n"));
        sb.append(colorize("&6/severshop sethome &7- 홈 슬롯 추가 구매\n"));
        sb.append(colorize("&6/severshop sethome info &7- 현재 홈 슬롯 정보\n"));
        sb.append(colorize("&6/severshop nickname <닉네임> &7- 닉네임 변경 구매\n"));
        sb.append(colorize("&6/severshop nickname info &7- 닉네임 정보 확인\n"));
        sb.append(colorize("&6/severshop nickname reset &7- 닉네임 초기화\n"));
        sb.append(colorize("&6/severshop anvil &7- 대장간 사용 권한 구매\n"));
        sb.append(colorize("&6/severshop craft &7- 작업대 사용 권한 구매\n"));
        sb.append(colorize("&6/severshop auction &7- 경매 한도 추가 구매\n"));
        sb.append(colorize("&6/severshop auction info &7- 경매 한도 정보\n"));
        sb.append(colorize("&7별칭: /buy, /ss\n"));

        if (sender.hasPermission("servershop.admin")) {
            sb.append(colorize("\n&c=== 관리자 명령어 ===\n"));
            sb.append(colorize("&6/severshop reload &7- 설정 다시 로드\n"));
            sb.append(colorize("&6/severshop sethome info <플레이어> &7- 다른 플레이어 홈 슬롯 확인\n"));
            sb.append(colorize("&6/severshop sethome top [페이지] &7- 홈 슬롯 순위\n"));
            sb.append(colorize("&6/severshop nickname set <플레이어> <닉네임> &7- 관리자 닉네임 설정\n"));
            sb.append(colorize("&6/severshop nickname resetcooldown <플레이어> &7- 쿨다운 초기화\n"));
            sb.append(colorize("&6/severshop nickname reset <플레이어> &7- 닉네임 초기화\n"));
            sb.append(colorize("&6/severshop auction info <플레이어> &7- 다른 플레이어 경매 한도 확인\n"));
            sb.append(colorize("&6/severshop auction top [페이지] &7- 경매 한도 순위"));
        }

        sender.sendMessage(sb.toString());
    }

    /**
     * Handle /severshop sethome [info [player]] [top [page]] command.
     */
    private boolean handleSethomeCommand(CommandSender sender, String[] args) {
        // /severshop sethome top [page] (admin only)
        if (args.length > 1 && args[1].equalsIgnoreCase("top")) {
            if (!sender.hasPermission("servershop.admin")) {
                sender.sendMessage(colorize("&c권한이 없습니다."));
                return true;
            }
            int page = 1;
            if (args.length > 2) {
                try {
                    page = Integer.parseInt(args[2]);
                    if (page < 1) {
                        sender.sendMessage(colorize("&c페이지 번호는 1 이상이어야 합니다."));
                        return true;
                    }
                } catch (NumberFormatException e) {
                    sender.sendMessage(colorize("&c페이지 번호는 1 이상이어야 합니다."));
                    return true;
                }
            }
            leaderboardManager.showSethomeLeaderboard(sender, page);
            return true;
        }

        // Must be a player for non-admin commands
        if (!(sender instanceof Player)) {
            sender.sendMessage(colorize(getMessage("sethome-console-error")));
            return true;
        }

        Player player = (Player) sender;
        com.nearoutpost.servershop.SetHomeSlotPurchaseHandler handler =
                new com.nearoutpost.servershop.SetHomeSlotPurchaseHandler(plugin);

        // Check for info subcommand
        if (args.length > 1 && args[1].equalsIgnoreCase("info")) {
            // Check for optional player name (for OPs)
            if (args.length > 2) {
                if (!sender.isOp()) {
                    sender.sendMessage(colorize("&c권한이 없습니다."));
                    return true;
                }
                return handler.showInfo(sender, args[2]);
            }
            return handler.showInfo(sender, null);
        }

        // Purchase next tier
        return handler.purchase(player);
    }

    /**
     * Handle /severshop nickname <set|resetcooldown|reset|info|nickname> command.
     * Subcommand keywords are checked FIRST to prevent the argument validation bug.
     */
    private boolean handleNicknameCommand(CommandSender sender, String[] args) {
        com.nearoutpost.servershop.NicknameChangeHandler handler =
                new com.nearoutpost.servershop.NicknameChangeHandler(plugin);

        if (args.length < 2) {
            sender.sendMessage(colorize(getMessage("nickname-usage-player")));
            return true;
        }

        String subcommand = args[1].toLowerCase();

        // 1. "set" — admin set nickname: /severshop nickname set <player> <nickname>
        if (subcommand.equals("set")) {
            if (!sender.hasPermission("servershop.nickname.admin")) {
                sender.sendMessage(colorize("&c권한이 없습니다."));
                return true;
            }
            if (args.length < 4) {
                sender.sendMessage(colorize("&c사용법: /severshop nickname set <플레이어> <닉네임>"));
                return true;
            }
            return handler.adminSetNickname(sender, args[2], args[3]);
        }

        // 2. "resetcooldown" — admin reset cooldown: /severshop nickname resetcooldown <player>
        if (subcommand.equals("resetcooldown")) {
            if (!sender.hasPermission("servershop.nickname.admin")) {
                sender.sendMessage(colorize("&c권한이 없습니다."));
                return true;
            }
            if (args.length < 3) {
                sender.sendMessage(colorize("&c사용법: /severshop nickname resetcooldown <플레이어>"));
                return true;
            }
            return handler.adminResetCooldown(sender, args[2]);
        }

        // 3. "reset" — reset nickname (self or admin for others)
        if (subcommand.equals("reset")) {
            // Admin reset for another player: /severshop nickname reset <player>
            if (args.length >= 3) {
                if (!sender.hasPermission("servershop.nickname.admin")) {
                    sender.sendMessage(colorize("&c권한이 없습니다."));
                    return true;
                }
                return handler.adminResetNickname(sender, args[2]);
            }
            // Self reset
            if (!(sender instanceof Player)) {
                sender.sendMessage(colorize(getMessage("nickname-console-error")));
                return true;
            }
            return handler.resetNickname((Player) sender);
        }

        // 4. "info" — show nickname info
        if (subcommand.equals("info")) {
            if (!(sender instanceof Player)) {
                sender.sendMessage(colorize(getMessage("nickname-console-error")));
                return true;
            }
            return handler.showInfo((Player) sender);
        }

        // 5. Fallback: treat as nickname purchase
        if (!(sender instanceof Player)) {
            sender.sendMessage(colorize(getMessage("nickname-console-error")));
            return true;
        }
        return handler.purchase((Player) sender, args[1]);
    }

    /**
     * Handle /severshop anvil [info] command.
     */
    private boolean handleAnvilCommand(CommandSender sender, String[] args) {
        if (!(sender instanceof Player)) {
            sender.sendMessage(colorize(getMessage("anvil-console-error")));
            return true;
        }

        Player player = (Player) sender;
        com.nearoutpost.servershop.AnvilAccessHandler handler =
                new com.nearoutpost.servershop.AnvilAccessHandler(plugin);

        if (args.length > 1 && args[1].equalsIgnoreCase("info")) {
            return handler.showInfo(player);
        }

        return handler.purchase(player);
    }

    /**
     * Handle /severshop craft [info] command.
     */
    private boolean handleCraftCommand(CommandSender sender, String[] args) {
        if (!(sender instanceof Player)) {
            sender.sendMessage(colorize(getMessage("craft-console-error")));
            return true;
        }

        Player player = (Player) sender;
        com.nearoutpost.servershop.CraftAccessHandler handler =
                new com.nearoutpost.servershop.CraftAccessHandler(plugin);

        if (args.length > 1 && args[1].equalsIgnoreCase("info")) {
            return handler.showInfo(player);
        }

        return handler.purchase(player);
    }

    /**
     * Handle /severshop auction [info [player]] [top [page]] command.
     */
    private boolean handleAuctionCommand(CommandSender sender, String[] args) {
        // /severshop auction top [page] (admin only)
        if (args.length > 1 && args[1].equalsIgnoreCase("top")) {
            if (!sender.hasPermission("servershop.admin")) {
                sender.sendMessage(colorize("&c권한이 없습니다."));
                return true;
            }
            int page = 1;
            if (args.length > 2) {
                try {
                    page = Integer.parseInt(args[2]);
                    if (page < 1) {
                        sender.sendMessage(colorize("&c페이지 번호는 1 이상이어야 합니다."));
                        return true;
                    }
                } catch (NumberFormatException e) {
                    sender.sendMessage(colorize("&c페이지 번호는 1 이상이어야 합니다."));
                    return true;
                }
            }
            leaderboardManager.showAuctionLeaderboard(sender, page);
            return true;
        }

        // /severshop auction info [player]
        if (args.length > 1 && args[1].equalsIgnoreCase("info")) {
            com.nearoutpost.servershop.AuctionLimitPurchaseHandler handler =
                    new com.nearoutpost.servershop.AuctionLimitPurchaseHandler(plugin);

            if (args.length > 2) {
                if (!sender.hasPermission("servershop.admin")) {
                    sender.sendMessage(colorize("&c권한이 없습니다."));
                    return true;
                }
                return handler.showInfo(sender, args[2]);
            }

            if (!(sender instanceof Player)) {
                sender.sendMessage(colorize(getMessage("auction-console-error")));
                return true;
            }
            return handler.showInfo((Player) sender);
        }

        // Purchase
        if (!(sender instanceof Player)) {
            sender.sendMessage(colorize(getMessage("auction-console-error")));
            return true;
        }

        com.nearoutpost.servershop.AuctionLimitPurchaseHandler handler =
                new com.nearoutpost.servershop.AuctionLimitPurchaseHandler(plugin);
        return handler.purchase((Player) sender);
    }

    /**
     * Get online player names filtered by prefix.
     */
    private List<String> getOnlinePlayerNames(String prefix) {
        return plugin.getServer().getOnlinePlayers().stream()
                .map(Player::getName)
                .filter(name -> name.toLowerCase().startsWith(prefix.toLowerCase()))
                .collect(Collectors.toList());
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
