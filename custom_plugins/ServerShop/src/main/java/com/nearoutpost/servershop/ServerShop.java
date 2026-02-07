package com.nearoutpost.servershop;

import net.milkbowl.vault.economy.Economy;
import org.bukkit.plugin.RegisteredServiceProvider;
import org.bukkit.plugin.java.JavaPlugin;

import com.nearoutpost.servershop.commands.BuyCommand;

public class ServerShop extends JavaPlugin {

    private static Economy economy = null;
    private LuckPermsIntegration luckPermsIntegration = null;
    private EssentialsIntegration essentialsIntegration = null;

    @Override
    public void onEnable() {
        // Save default config
        saveDefaultConfig();

        // Setup economy
        if (!setupEconomy()) {
            getLogger().severe("Vault economy not found! Disabling plugin...");
            getServer().getPluginManager().disablePlugin(this);
            return;
        }

        // Setup LuckPerms
        luckPermsIntegration = new LuckPermsIntegration(this);
        if (!luckPermsIntegration.setupLuckPerms()) {
            getLogger().severe("LuckPerms not found! Disabling plugin...");
            getLogger().severe("This plugin requires LuckPerms for permission management.");
            getServer().getPluginManager().disablePlugin(this);
            return;
        }

        // Setup Essentials (optional - for nickname changes)
        essentialsIntegration = new EssentialsIntegration(this);
        if (essentialsIntegration.setupEssentials()) {
            getLogger().info("EssentialsX integration enabled for nickname changes");
        } else {
            getLogger().warning("EssentialsX not found - nickname change feature disabled");
        }

        // Validate config
        try {
            new ConfigValidator(this).validate();
        } catch (ConfigValidator.ConfigException e) {
            getLogger().severe("Config validation failed: " + e.getMessage());
            getLogger().severe("Plugin will continue but sethome purchases may not work correctly!");
            getLogger().severe("Please fix your config.yml and reload the plugin.");
        }

        // Register commands
        getCommand("severshop").setExecutor(new BuyCommand(this));

        getLogger().info("ServerShop v" + getDescription().getVersion() + " enabled! Economy: " + economy.getName());
        getLogger().info("LuckPerms integration enabled for permission management");
    }

    @Override
    public void onDisable() {
        getLogger().info("ServerShop disabled.");
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

    public static Economy getEconomy() {
        return economy;
    }

    public LuckPermsIntegration getLuckPermsIntegration() {
        return luckPermsIntegration;
    }

    public EssentialsIntegration getEssentialsIntegration() {
        return essentialsIntegration;
    }
}
