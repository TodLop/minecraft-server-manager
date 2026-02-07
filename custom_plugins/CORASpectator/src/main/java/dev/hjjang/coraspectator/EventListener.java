package dev.hjjang.coraspectator;

import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerCommandPreprocessEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.event.player.PlayerTeleportEvent;

public class EventListener implements Listener {
    private final SpectatorManager spectatorManager;

    public EventListener(SpectatorManager spectatorManager) {
        this.spectatorManager = spectatorManager;
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onPlayerTeleport(PlayerTeleportEvent event) {
        Player player = event.getPlayer();
        String playerName = player.getName();

        if (!spectatorManager.isInSession(playerName)) {
            return;
        }

        SpectatorSession session = spectatorManager.getSession(playerName);
        if (session == null) {
            return;
        }

        Player target = Bukkit.getPlayer(session.getTargetName());

        if (target == null || !target.isOnline()) {
            return;
        }

        double distance = event.getTo().distance(target.getLocation());

        if (distance > 100) {
            event.setCancelled(true);
            player.sendMessage(ChatColor.RED + "You can only follow your assigned target during the spectator session.");
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onPlayerCommand(PlayerCommandPreprocessEvent event) {
        Player player = event.getPlayer();
        String playerName = player.getName();

        if (!spectatorManager.isInSession(playerName)) {
            return;
        }

        String command = event.getMessage().toLowerCase();

        if (command.startsWith("/cora-spectate end")) {
            return;
        }

        event.setCancelled(true);
        player.sendMessage(ChatColor.RED + "Commands are disabled during spectator session. Use /cora-spectate end to exit.");
    }

    @EventHandler
    public void onPlayerQuit(PlayerQuitEvent event) {
        String playerName = event.getPlayer().getName();
        spectatorManager.handlePlayerQuit(playerName);
    }
}
