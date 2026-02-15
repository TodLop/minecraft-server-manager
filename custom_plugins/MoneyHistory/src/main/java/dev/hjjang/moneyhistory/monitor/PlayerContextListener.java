package dev.hjjang.moneyhistory.monitor;

import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerCommandPreprocessEvent;
import org.bukkit.event.player.PlayerQuitEvent;

public class PlayerContextListener implements Listener {
    private final AttributionResolver attributionResolver;

    public PlayerContextListener(AttributionResolver attributionResolver) {
        this.attributionResolver = attributionResolver;
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onPlayerCommand(PlayerCommandPreprocessEvent event) {
        Player player = event.getPlayer();
        String command = event.getMessage(); // Includes the "/" prefix

        // Only track relevant commands for attribution
        String lowerCommand = command.toLowerCase();
        if (lowerCommand.startsWith("/auction") ||
            lowerCommand.startsWith("/pay") ||
            lowerCommand.startsWith("/buy") ||
            lowerCommand.startsWith("/sell") ||
            lowerCommand.startsWith("/eco") ||
            lowerCommand.startsWith("/economy") ||
            lowerCommand.startsWith("/uc") ||
            lowerCommand.startsWith("/ultracosmetics")) {

            PlayerContext context = attributionResolver.getOrCreateContext(player.getUniqueId());
            context.recordCommand(command);
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPlayerQuit(PlayerQuitEvent event) {
        // Clean up player context when they leave to save memory
        attributionResolver.removeContext(event.getPlayer().getUniqueId());
    }
}
