package dev.hjjang.moneyhistory.format;

import dev.hjjang.moneyhistory.model.HistoryEntry;
import dev.hjjang.moneyhistory.model.Source;
import dev.hjjang.moneyhistory.util.TimeFormatter;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;

import java.util.ArrayList;
import java.util.List;

public class PlayerFormatter {
    public static List<Component> formatHistory(String playerName, List<HistoryEntry> entries,
                                               int page, int totalPages, int totalEntries,
                                               double currentBalance, boolean useRelativeTime, boolean showUnknownHelp) {
        List<Component> lines = new ArrayList<>();

        // Header
        lines.add(Component.text("=".repeat(49), NamedTextColor.GRAY));
        lines.add(Component.text("Money History for ", NamedTextColor.YELLOW)
                .append(Component.text(playerName, NamedTextColor.GOLD, TextDecoration.BOLD))
                .append(Component.text(" (Page " + page + "/" + totalPages + ")", NamedTextColor.YELLOW)));

        // Current Balance - prominently displayed
        String balanceStr = String.format("Current Balance: %,.2f", currentBalance);
        lines.add(Component.text(balanceStr, NamedTextColor.GREEN, TextDecoration.BOLD));

        lines.add(Component.text("=".repeat(49), NamedTextColor.GRAY));

        // Empty state
        if (entries.isEmpty()) {
            lines.add(Component.text("No balance history found.", NamedTextColor.GRAY, TextDecoration.ITALIC));
        }

        // Entries
        for (HistoryEntry entry : entries) {
            lines.add(formatEntry(entry, useRelativeTime));

            // Show unknown help for first unknown entry
            if (showUnknownHelp && entry.getSource() == Source.UNKNOWN && entries.indexOf(entry) == 0) {
                lines.add(Component.text("  Tip: Unknown sources can be player auctions, shop purchases,", NamedTextColor.DARK_GRAY));
                lines.add(Component.text("  or admin commands. Use --source filter to refine results.", NamedTextColor.DARK_GRAY));
            }
        }

        // Footer
        if (!entries.isEmpty()) {
            lines.add(Component.text("=".repeat(49), NamedTextColor.GRAY));

            // Pagination controls
            Component pagination = Component.text("");
            if (page > 1) {
                pagination = pagination.append(Component.text("<< Previous", NamedTextColor.AQUA)
                        .hoverEvent(Component.text("Click to go to page " + (page - 1)))
                        .clickEvent(net.kyori.adventure.text.event.ClickEvent.runCommand("/mh " + playerName + " " + (page - 1))))
                        .append(Component.text(" | ", NamedTextColor.GRAY));
            }

            pagination = pagination.append(Component.text("Page " + page + "/" + totalPages, NamedTextColor.YELLOW));

            if (page < totalPages) {
                pagination = pagination.append(Component.text(" | ", NamedTextColor.GRAY))
                        .append(Component.text("Next >>", NamedTextColor.AQUA)
                                .hoverEvent(Component.text("Click to go to page " + (page + 1)))
                                .clickEvent(net.kyori.adventure.text.event.ClickEvent.runCommand("/mh " + playerName + " " + (page + 1))));
            }

            lines.add(pagination);

            // Entry count
            int startEntry = (page - 1) * entries.size() + 1;
            int endEntry = startEntry + entries.size() - 1;
            lines.add(Component.text("Total entries: " + totalEntries + " | Showing " + startEntry + "-" + endEntry, NamedTextColor.GRAY));
            lines.add(Component.text("=".repeat(49), NamedTextColor.GRAY));
        }

        return lines;
    }

    private static Component formatEntry(HistoryEntry entry, boolean useRelativeTime) {
        Component line = Component.text("");

        // Timestamp
        String timeStr = useRelativeTime ?
                TimeFormatter.formatRelative(entry.getTimestampMs()) :
                TimeFormatter.formatDisplay(entry.getTimestampMs());

        line = line.append(Component.text("[" + timeStr + "] ", NamedTextColor.GRAY));

        // Delta (colored based on positive/negative)
        double delta = entry.getDelta();
        NamedTextColor deltaColor = delta >= 0 ? NamedTextColor.GREEN : NamedTextColor.RED;
        String deltaStr = String.format("%+,.2f", delta);

        line = line.append(Component.text(deltaStr, deltaColor, TextDecoration.BOLD))
                .append(Component.text(" | ", NamedTextColor.DARK_GRAY));

        // Balance
        String balanceStr = String.format("Bal: %,.2f", entry.getBalanceAfter());
        line = line.append(Component.text(balanceStr, NamedTextColor.YELLOW));

        // Add to list
        List<Component> result = new ArrayList<>();
        result.add(line);

        // Source (indented on next line)
        Component sourceLine = Component.text("  Source: ", NamedTextColor.DARK_GRAY)
                .append(Component.text(entry.getSource().getDisplayName(), getSourceColor(entry.getSource())));

        if (entry.getDetails() != null && !entry.getDetails().isEmpty()) {
            sourceLine = sourceLine.append(Component.text(" (" + entry.getDetails() + ")", NamedTextColor.GRAY));
        }

        result.add(sourceLine);

        return line.append(Component.newline()).append(sourceLine);
    }

    private static NamedTextColor getSourceColor(Source source) {
        switch (source) {
            case PLAYER_AUCTION:
                return NamedTextColor.LIGHT_PURPLE;
            case ESSENTIALS_PAY:
            case ESSENTIALS_RECEIVE:
                return NamedTextColor.AQUA;
            case SERVER_SHOP:
                return NamedTextColor.GOLD;
            case ADMIN_COMMAND:
                return NamedTextColor.RED;
            case LIKELY_ADMIN_COMMAND:
                return NamedTextColor.DARK_RED;
            case OFFLINE_CHANGE:
                return NamedTextColor.BLUE;
            case UNKNOWN:
            default:
                return NamedTextColor.GRAY;
        }
    }
}
