package dev.hjjang.moneyhistory.model;

import java.util.UUID;

public class HistoryEntry {
    private final long id;
    private final UUID playerUuid;
    private final String playerName;
    private final long timestampMs;
    private final double balanceBefore;
    private final double balanceAfter;
    private final double delta;
    private final Source source;
    private final String details;

    public HistoryEntry(long id, UUID playerUuid, String playerName, long timestampMs,
                       double balanceBefore, double balanceAfter, double delta,
                       Source source, String details) {
        this.id = id;
        this.playerUuid = playerUuid;
        this.playerName = playerName;
        this.timestampMs = timestampMs;
        this.balanceBefore = balanceBefore;
        this.balanceAfter = balanceAfter;
        this.delta = delta;
        this.source = source;
        this.details = details;
    }

    public long getId() {
        return id;
    }

    public UUID getPlayerUuid() {
        return playerUuid;
    }

    public String getPlayerName() {
        return playerName;
    }

    public long getTimestampMs() {
        return timestampMs;
    }

    public double getBalanceBefore() {
        return balanceBefore;
    }

    public double getBalanceAfter() {
        return balanceAfter;
    }

    public double getDelta() {
        return delta;
    }

    public Source getSource() {
        return source;
    }

    public String getDetails() {
        return details;
    }
}
