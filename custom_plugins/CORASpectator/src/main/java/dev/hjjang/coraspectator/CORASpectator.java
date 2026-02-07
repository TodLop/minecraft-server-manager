package dev.hjjang.coraspectator;

import org.bukkit.plugin.java.JavaPlugin;

public class CORASpectator extends JavaPlugin {
    private SpectatorManager spectatorManager;
    private SessionLogger sessionLogger;

    @Override
    public void onEnable() {
        sessionLogger = new SessionLogger(getDataFolder());

        spectatorManager = new SpectatorManager(this, sessionLogger);

        EventListener eventListener = new EventListener(spectatorManager);
        getServer().getPluginManager().registerEvents(eventListener, this);

        RCONCommandHandler commandHandler = new RCONCommandHandler(spectatorManager);
        getCommand("cora-spectate").setExecutor(commandHandler);

        getLogger().info("CORASpectator enabled!");
    }

    @Override
    public void onDisable() {
        if (spectatorManager != null) {
            spectatorManager.endAllSessions();
        }

        getLogger().info("CORASpectator disabled.");
    }

    public SpectatorManager getSpectatorManager() {
        return spectatorManager;
    }
}
