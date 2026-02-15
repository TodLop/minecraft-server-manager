package dev.hjjang.serveraccount;

import net.milkbowl.vault.economy.Economy;
import net.milkbowl.vault.economy.EconomyResponse;

public class AccountManager {
    private final Economy economy;
    private final String accountName;
    private final TransactionDatabase database;

    public AccountManager(Economy economy, String accountName, TransactionDatabase database) {
        this.economy = economy;
        this.accountName = accountName;
        this.database = database;
    }

    public void ensureAccountExists() {
        if (!economy.hasAccount(accountName)) {
            economy.createPlayerAccount(accountName);
        }
    }

    public double getBalance() {
        return economy.getBalance(accountName);
    }

    public boolean deposit(double amount, String sourcePlugin, String playerName, String reason) {
        EconomyResponse response = economy.depositPlayer(accountName, amount);
        if (response.transactionSuccess()) {
            database.recordTransaction("DEPOSIT", amount, sourcePlugin, playerName, null, reason, response.balance);
            return true;
        }
        return false;
    }

    public boolean withdraw(double amount, String adminName, String reason) {
        EconomyResponse response = economy.withdrawPlayer(accountName, amount);
        if (response.transactionSuccess()) {
            database.recordTransaction("WITHDRAWAL", amount, null, null, adminName, reason, response.balance);
            return true;
        }
        return false;
    }

    public boolean payPlayer(String playerName, double amount, String adminName, String reason) {
        // Withdraw from server account
        EconomyResponse withdrawResponse = economy.withdrawPlayer(accountName, amount);
        if (!withdrawResponse.transactionSuccess()) {
            return false;
        }

        // Deposit to player
        EconomyResponse depositResponse = economy.depositPlayer(playerName, amount);
        if (!depositResponse.transactionSuccess()) {
            // Refund server account
            economy.depositPlayer(accountName, amount);
            return false;
        }

        database.recordTransaction("PAY_PLAYER", amount, null, playerName, adminName, reason, withdrawResponse.balance);
        return true;
    }

    public boolean manualDeposit(double amount, String adminName, String reason) {
        EconomyResponse response = economy.depositPlayer(accountName, amount);
        if (response.transactionSuccess()) {
            database.recordTransaction("DEPOSIT", amount, "Manual", null, adminName, reason, response.balance);
            return true;
        }
        return false;
    }

    public boolean manualWithdraw(double amount, String adminName, String reason) {
        EconomyResponse response = economy.withdrawPlayer(accountName, amount);
        if (response.transactionSuccess()) {
            database.recordTransaction("WITHDRAWAL", amount, "Manual", null, adminName, reason, response.balance);
            return true;
        }
        return false;
    }

    public String getAccountName() {
        return accountName;
    }
}
