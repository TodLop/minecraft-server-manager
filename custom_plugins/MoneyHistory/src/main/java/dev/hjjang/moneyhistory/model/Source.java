package dev.hjjang.moneyhistory.model;

public enum Source {
    PLAYER_AUCTION("PlayerAuctions"),
    ESSENTIALS_PAY("Essentials (/pay)"),
    ESSENTIALS_RECEIVE("Essentials (received)"),
    ESSENTIALS_SELL("Essentials (/sell)"),
    SERVER_SHOP("ServerShop"),
    ADMIN_COMMAND("Admin Command"),
    LIKELY_ADMIN_COMMAND("Likely Admin Command"),
    OFFLINE_CHANGE("Offline Change"),
    UNKNOWN("Unknown");

    private final String displayName;

    Source(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }

    @Override
    public String toString() {
        return displayName;
    }
}
