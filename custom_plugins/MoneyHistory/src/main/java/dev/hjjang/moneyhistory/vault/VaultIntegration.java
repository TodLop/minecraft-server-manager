package dev.hjjang.moneyhistory.vault;

import dev.hjjang.moneyhistory.MoneyHistoryPlugin;
import net.milkbowl.vault.economy.Economy;
import org.bukkit.plugin.RegisteredServiceProvider;

public class VaultIntegration {
    private final MoneyHistoryPlugin plugin;
    private Economy economy;

    public VaultIntegration(MoneyHistoryPlugin plugin) {
        this.plugin = plugin;
    }

    public boolean setupEconomy() {
        if (plugin.getServer().getPluginManager().getPlugin("Vault") == null) {
            plugin.getLogger().severe("Vault plugin not found!");
            return false;
        }

        RegisteredServiceProvider<Economy> rsp = plugin.getServer().getServicesManager().getRegistration(Economy.class);
        if (rsp == null) {
            plugin.getLogger().severe("No economy provider found!");
            return false;
        }

        economy = rsp.getProvider();
        return economy != null;
    }

    public Economy getEconomy() {
        return economy;
    }

    public String getEconomyName() {
        if (economy == null) {
            return "None";
        }
        return economy.getName();
    }

    public boolean isAvailable() {
        return economy != null;
    }
}
