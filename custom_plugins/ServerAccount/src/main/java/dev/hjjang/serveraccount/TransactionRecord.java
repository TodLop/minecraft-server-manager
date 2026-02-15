package dev.hjjang.serveraccount;

public class TransactionRecord {
    private final int id;
    private final long timestampMs;
    private final String type;
    private final double amount;
    private final String sourcePlugin;
    private final String playerName;
    private final String adminName;
    private final String reason;
    private final double balanceAfter;

    public TransactionRecord(int id, long timestampMs, String type, double amount,
                             String sourcePlugin, String playerName, String adminName,
                             String reason, double balanceAfter) {
        this.id = id;
        this.timestampMs = timestampMs;
        this.type = type;
        this.amount = amount;
        this.sourcePlugin = sourcePlugin;
        this.playerName = playerName;
        this.adminName = adminName;
        this.reason = reason;
        this.balanceAfter = balanceAfter;
    }

    public int getId() { return id; }
    public long getTimestampMs() { return timestampMs; }
    public String getType() { return type; }
    public double getAmount() { return amount; }
    public String getSourcePlugin() { return sourcePlugin; }
    public String getPlayerName() { return playerName; }
    public String getAdminName() { return adminName; }
    public String getReason() { return reason; }
    public double getBalanceAfter() { return balanceAfter; }
}
