package dev.hjjang.serveraccount;

import dev.hjjang.serveraccount.api.ServerAccountAPI;
import net.milkbowl.vault.economy.Economy;
import org.bukkit.plugin.RegisteredServiceProvider;
import org.bukkit.plugin.java.JavaPlugin;

public class ServerAccountPlugin extends JavaPlugin {
    private Economy economy;
    private AccountManager accountManager;
    private TransactionDatabase transactionDatabase;

    @Override
    public void onEnable() {
        saveDefaultConfig();

        // Setup Vault economy
        if (!setupEconomy()) {
            getLogger().severe("Vault economy not found! Disabling plugin...");
            getServer().getPluginManager().disablePlugin(this);
            return;
        }

        // Initialize database
        transactionDatabase = new TransactionDatabase(getDataFolder(), getLogger());

        // Initialize account manager
        String accountName = getConfig().getString("account-name", "nearoutpost");
        accountManager = new AccountManager(economy, accountName, transactionDatabase);
        accountManager.ensureAccountExists();

        // Initialize static API
        ServerAccountAPI.init(this);

        // Register commands
        ServerAccountCommand commandHandler = new ServerAccountCommand(this);
        getCommand("serveraccount").setExecutor(commandHandler);
        getCommand("serveraccount").setTabCompleter(commandHandler);

        getLogger().info("ServerAccount v" + getDescription().getVersion() + " enabled!");
        getLogger().info("Treasury account: " + accountName + " (balance: " + String.format("%.2f", accountManager.getBalance()) + ")");
    }

    @Override
    public void onDisable() {
        if (transactionDatabase != null) {
            transactionDatabase.close();
        }
        getLogger().info("ServerAccount disabled.");
    }

    private boolean setupEconomy() {
        if (getServer().getPluginManager().getPlugin("Vault") == null) {
            return false;
        }
        RegisteredServiceProvider<Economy> rsp = getServer().getServicesManager().getRegistration(Economy.class);
        if (rsp == null) {
            return false;
        }
        economy = rsp.getProvider();
        return economy != null;
    }

    public Economy getEconomy() {
        return economy;
    }

    public AccountManager getAccountManager() {
        return accountManager;
    }

    public TransactionDatabase getTransactionDatabase() {
        return transactionDatabase;
    }
}
