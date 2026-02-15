package dev.hjjang.serveraccount;

import org.bukkit.ChatColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.List;
import java.util.stream.Collectors;

public class ServerAccountCommand implements CommandExecutor, TabCompleter {
    private final ServerAccountPlugin plugin;

    public ServerAccountCommand(ServerAccountPlugin plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (args.length < 1) {
            showHelp(sender);
            return true;
        }

        String sub = args[0].toLowerCase();

        switch (sub) {
            case "balance", "bal" -> handleBalance(sender);
            case "pay" -> handlePay(sender, args);
            case "deposit" -> handleDeposit(sender, args);
            case "withdraw" -> handleWithdraw(sender, args);
            case "history" -> handleHistory(sender, args);
            case "reload" -> handleReload(sender);
            default -> showHelp(sender);
        }

        return true;
    }

    private void handleBalance(CommandSender sender) {
        double balance = plugin.getAccountManager().getBalance();
        sender.sendMessage(colorize("&6[서버계좌] &e잔액: &a" + String.format("%.2f", balance) + "원"));
    }

    private void handlePay(CommandSender sender, String[] args) {
        if (args.length < 3) {
            sender.sendMessage(colorize("&c사용법: /sa pay <플레이어> <금액> [사유...]"));
            return;
        }

        String playerName = args[1];
        double amount;
        try {
            amount = Double.parseDouble(args[2]);
            if (amount <= 0) {
                sender.sendMessage(colorize("&c금액은 0보다 커야 합니다."));
                return;
            }
        } catch (NumberFormatException e) {
            sender.sendMessage(colorize("&c올바른 금액을 입력해주세요."));
            return;
        }

        String reason = args.length > 3 ? String.join(" ", Arrays.copyOfRange(args, 3, args.length)) : null;

        boolean success = plugin.getAccountManager().payPlayer(playerName, amount, sender.getName(), reason);
        if (success) {
            sender.sendMessage(colorize("&6[서버계좌] &a" + playerName + "에게 " + String.format("%.2f", amount) + "원을 지급했습니다."));
            if (reason != null) {
                sender.sendMessage(colorize("&7사유: " + reason));
            }
            plugin.getLogger().info(sender.getName() + " paid " + playerName + " " + amount + " from server account" +
                (reason != null ? " (reason: " + reason + ")" : ""));
        } else {
            sender.sendMessage(colorize("&c지급 실패! 잔액이 부족하거나 플레이어를 찾을 수 없습니다."));
        }
    }

    private void handleDeposit(CommandSender sender, String[] args) {
        if (args.length < 2) {
            sender.sendMessage(colorize("&c사용법: /sa deposit <금액> [사유...]"));
            return;
        }

        double amount;
        try {
            amount = Double.parseDouble(args[1]);
            if (amount <= 0) {
                sender.sendMessage(colorize("&c금액은 0보다 커야 합니다."));
                return;
            }
        } catch (NumberFormatException e) {
            sender.sendMessage(colorize("&c올바른 금액을 입력해주세요."));
            return;
        }

        String reason = args.length > 2 ? String.join(" ", Arrays.copyOfRange(args, 2, args.length)) : null;

        boolean success = plugin.getAccountManager().manualDeposit(amount, sender.getName(), reason);
        if (success) {
            sender.sendMessage(colorize("&6[서버계좌] &a" + String.format("%.2f", amount) + "원을 입금했습니다."));
            plugin.getLogger().info(sender.getName() + " deposited " + amount + " to server account" +
                (reason != null ? " (reason: " + reason + ")" : ""));
        } else {
            sender.sendMessage(colorize("&c입금 실패!"));
        }
    }

    private void handleWithdraw(CommandSender sender, String[] args) {
        if (args.length < 2) {
            sender.sendMessage(colorize("&c사용법: /sa withdraw <금액> [사유...]"));
            return;
        }

        double amount;
        try {
            amount = Double.parseDouble(args[1]);
            if (amount <= 0) {
                sender.sendMessage(colorize("&c금액은 0보다 커야 합니다."));
                return;
            }
        } catch (NumberFormatException e) {
            sender.sendMessage(colorize("&c올바른 금액을 입력해주세요."));
            return;
        }

        String reason = args.length > 2 ? String.join(" ", Arrays.copyOfRange(args, 2, args.length)) : null;

        boolean success = plugin.getAccountManager().manualWithdraw(amount, sender.getName(), reason);
        if (success) {
            sender.sendMessage(colorize("&6[서버계좌] &a" + String.format("%.2f", amount) + "원을 출금했습니다."));
            plugin.getLogger().info(sender.getName() + " withdrew " + amount + " from server account" +
                (reason != null ? " (reason: " + reason + ")" : ""));
        } else {
            sender.sendMessage(colorize("&c출금 실패! 잔액이 부족합니다."));
        }
    }

    private void handleHistory(CommandSender sender, String[] args) {
        int page = 1;
        if (args.length > 1) {
            try {
                page = Integer.parseInt(args[1]);
                if (page < 1) page = 1;
            } catch (NumberFormatException e) {
                sender.sendMessage(colorize("&c올바른 페이지 번호를 입력해주세요."));
                return;
            }
        }

        int perPage = plugin.getConfig().getInt("history-per-page", 10);
        int totalCount = plugin.getTransactionDatabase().getTotalCount();
        int totalPages = Math.max(1, (int) Math.ceil((double) totalCount / perPage));

        if (page > totalPages) {
            sender.sendMessage(colorize("&c페이지 " + page + "는 존재하지 않습니다. (최대: " + totalPages + ")"));
            return;
        }

        List<TransactionRecord> records = plugin.getTransactionDatabase().getHistory(page, perPage);

        sender.sendMessage(colorize("&6=== 서버계좌 거래 내역 (&e" + page + "&6/&e" + totalPages + "&6) ==="));

        if (records.isEmpty()) {
            sender.sendMessage(colorize("&7거래 내역이 없습니다."));
            return;
        }

        SimpleDateFormat sdf = new SimpleDateFormat("MM/dd HH:mm");

        for (TransactionRecord record : records) {
            String time = sdf.format(new Date(record.getTimestampMs()));
            String typeColor = switch (record.getType()) {
                case "DEPOSIT" -> "&a+";
                case "WITHDRAWAL" -> "&c-";
                case "PAY_PLAYER" -> "&e-";
                default -> "&7";
            };

            StringBuilder line = new StringBuilder();
            line.append("&7[").append(time).append("] ");
            line.append(typeColor).append(String.format("%.2f", record.getAmount()));

            if (record.getSourcePlugin() != null) {
                line.append(" &7(").append(record.getSourcePlugin()).append(")");
            }
            if (record.getPlayerName() != null) {
                line.append(" &7-> ").append(record.getPlayerName());
            }
            if (record.getAdminName() != null) {
                line.append(" &7by ").append(record.getAdminName());
            }
            if (record.getReason() != null) {
                line.append(" &8\"").append(record.getReason()).append("\"");
            }

            sender.sendMessage(colorize(line.toString()));
        }

        sender.sendMessage(colorize("&6잔액: &a" + String.format("%.2f", plugin.getAccountManager().getBalance()) + "원"));
    }

    private void handleReload(CommandSender sender) {
        plugin.reloadConfig();
        sender.sendMessage(colorize("&6[서버계좌] &a설정을 다시 로드했습니다."));
    }

    private void showHelp(CommandSender sender) {
        sender.sendMessage(colorize("&6=== 서버계좌 명령어 ==="));
        sender.sendMessage(colorize("&6/sa balance &7- 잔액 확인"));
        sender.sendMessage(colorize("&6/sa pay <플레이어> <금액> [사유] &7- 플레이어에게 지급"));
        sender.sendMessage(colorize("&6/sa deposit <금액> [사유] &7- 수동 입금"));
        sender.sendMessage(colorize("&6/sa withdraw <금액> [사유] &7- 수동 출금"));
        sender.sendMessage(colorize("&6/sa history [페이지] &7- 거래 내역"));
        sender.sendMessage(colorize("&6/sa reload &7- 설정 다시 로드"));
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        List<String> completions = new ArrayList<>();

        if (args.length == 1) {
            String input = args[0].toLowerCase();
            List<String> subs = List.of("balance", "pay", "deposit", "withdraw", "history", "reload");
            completions.addAll(subs.stream().filter(s -> s.startsWith(input)).collect(Collectors.toList()));
        } else if (args.length == 2 && args[0].equalsIgnoreCase("pay")) {
            // Suggest online player names
            String input = args[1].toLowerCase();
            completions.addAll(plugin.getServer().getOnlinePlayers().stream()
                .map(p -> p.getName())
                .filter(name -> name.toLowerCase().startsWith(input))
                .collect(Collectors.toList()));
        }

        return completions;
    }

    private String colorize(String message) {
        return ChatColor.translateAlternateColorCodes('&', message);
    }
}
