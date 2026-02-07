package dev.hjjang.moneyhistory.format;

import dev.hjjang.moneyhistory.model.HistoryEntry;
import dev.hjjang.moneyhistory.util.TimeFormatter;

import java.util.ArrayList;
import java.util.List;

public class ConsoleFormatter {
    private static final String PREFIX = "[MoneyHistory] ";

    public static List<String> formatHistory(String playerName, List<HistoryEntry> entries,
                                            int page, int totalPages, int totalEntries, double currentBalance) {
        List<String> lines = new ArrayList<>();

        // Header
        lines.add(PREFIX + "History for " + playerName + " (Page " + page + "/" + totalPages + ")");

        // Current Balance - prominently displayed
        String balanceStr = String.format("Current Balance: %,.2f", currentBalance);
        lines.add(PREFIX + balanceStr);

        // Empty state
        if (entries.isEmpty()) {
            lines.add(PREFIX + "No balance history found.");
            return lines;
        }

        // Entries
        for (HistoryEntry entry : entries) {
            String timestamp = TimeFormatter.formatAbsolute(entry.getTimestampMs());
            String delta = String.format("%+,.2f", entry.getDelta());
            String balance = String.format("%.2f", entry.getBalanceAfter());
            String source = entry.getSource().name();

            String line = String.format("%s%s | %s | Balance: %s | Source: %s",
                    PREFIX, timestamp, delta, balance, source);

            if (entry.getDetails() != null && !entry.getDetails().isEmpty()) {
                line += " | " + entry.getDetails();
            }

            lines.add(line);
        }

        // Footer
        int startEntry = (page - 1) * entries.size() + 1;
        int endEntry = startEntry + entries.size() - 1;
        lines.add(PREFIX + "Total entries: " + totalEntries + " | Page " + page + "/" + totalPages +
                " | Showing " + startEntry + "-" + endEntry);

        return lines;
    }

    public static List<String> formatError(String message) {
        List<String> lines = new ArrayList<>();
        lines.add(PREFIX + "Error: " + message);
        return lines;
    }

    public static List<String> formatSuccess(String message) {
        List<String> lines = new ArrayList<>();
        lines.add(PREFIX + message);
        return lines;
    }
}
