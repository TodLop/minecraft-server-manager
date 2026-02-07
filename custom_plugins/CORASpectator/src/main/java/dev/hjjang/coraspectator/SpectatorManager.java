package dev.hjjang.coraspectator;

import org.bukkit.Bukkit;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.plugin.Plugin;
import org.bukkit.scheduler.BukkitTask;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Map;

public class SpectatorManager {
    private final Plugin plugin;
    private final SessionLogger logger;
    private final Map<String, SpectatorSession> activeSessions;
    private final Map<String, BukkitTask> timeoutTasks;
    private static final DateTimeFormatter ISO_FORMAT = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    public SpectatorManager(Plugin plugin, SessionLogger logger) {
        this.plugin = plugin;
        this.logger = logger;
        this.activeSessions = new HashMap<>();
        this.timeoutTasks = new HashMap<>();
    }

    public String startSession(String staffName, String targetName, int durationSeconds) {
        Player staff = Bukkit.getPlayer(staffName);
        Player target = Bukkit.getPlayer(targetName);

        if (staff == null) {
            return "ERROR: Staff player '" + staffName + "' is not online";
        }

        if (target == null) {
            return "ERROR: Target player '" + targetName + "' is not online";
        }

        if (activeSessions.containsKey(staffName)) {
            return "ERROR: Staff player '" + staffName + "' is already in a spectator session";
        }

        Location originalLocation = staff.getLocation().clone();
        GameMode originalGameMode = staff.getGameMode();
        ItemStack[] originalInventory = staff.getInventory().getContents().clone();
        ItemStack[] originalArmorContents = staff.getInventory().getArmorContents().clone();
        double originalHealth = staff.getHealth();
        int originalFoodLevel = staff.getFoodLevel();
        float originalSaturation = staff.getSaturation();

        SpectatorSession session = new SpectatorSession(
                staffName, targetName, originalLocation, originalGameMode,
                originalInventory, originalArmorContents, originalHealth,
                originalFoodLevel, originalSaturation, durationSeconds
        );

        activeSessions.put(staffName, session);

        staff.setGameMode(GameMode.SPECTATOR);
        staff.teleport(target.getLocation());

        BukkitTask timeoutTask = Bukkit.getScheduler().runTaskLater(plugin, () -> {
            endSession(staffName, "timeout");
        }, durationSeconds * 20L);

        timeoutTasks.put(staffName, timeoutTask);

        logger.logStart(staffName, targetName, durationSeconds);

        return "SUCCESS: Spectator session started for " + staffName + " targeting " + targetName + " for " + durationSeconds + " seconds";
    }

    public String endSession(String staffName) {
        return endSession(staffName, "manual");
    }

    public String endSession(String staffName, String reason) {
        SpectatorSession session = activeSessions.get(staffName);

        if (session == null) {
            return "ERROR: No active spectator session found for '" + staffName + "'";
        }

        Player staff = Bukkit.getPlayer(staffName);

        if (staff != null && staff.isOnline()) {
            staff.teleport(session.getOriginalLocation());
            staff.setGameMode(session.getOriginalGameMode());
            staff.getInventory().setContents(session.getOriginalInventory());
            staff.getInventory().setArmorContents(session.getOriginalArmorContents());
            staff.setHealth(Math.min(session.getOriginalHealth(), staff.getMaxHealth()));
            staff.setFoodLevel(session.getOriginalFoodLevel());
            staff.setSaturation(session.getOriginalSaturation());
        }

        BukkitTask timeoutTask = timeoutTasks.get(staffName);
        if (timeoutTask != null) {
            timeoutTask.cancel();
            timeoutTasks.remove(staffName);
        }

        activeSessions.remove(staffName);

        if (reason.equals("timeout")) {
            logger.logTimeout(staffName, session.getTargetName());
        } else {
            logger.logEnd(staffName, session.getTargetName(), reason);
        }

        return "SUCCESS: Spectator session ended for " + staffName;
    }

    public String getStatus() {
        if (activeSessions.isEmpty()) {
            return "[]";
        }

        StringBuilder json = new StringBuilder("[");
        boolean first = true;

        for (SpectatorSession session : activeSessions.values()) {
            if (!first) {
                json.append(", ");
            }
            first = false;

            String startedAt = LocalDateTime.now()
                    .minusSeconds((System.currentTimeMillis() - session.getStartTime()) / 1000)
                    .format(ISO_FORMAT);

            json.append(String.format(
                    "{\"staff\": \"%s\", \"target\": \"%s\", \"started_at\": \"%s\", \"remaining_seconds\": %d}",
                    session.getStaffName(),
                    session.getTargetName(),
                    startedAt,
                    session.getRemainingSeconds()
            ));
        }

        json.append("]");
        return json.toString();
    }

    public boolean isInSession(String playerName) {
        return activeSessions.containsKey(playerName);
    }

    public SpectatorSession getSession(String playerName) {
        return activeSessions.get(playerName);
    }

    public void handlePlayerQuit(String playerName) {
        if (activeSessions.containsKey(playerName)) {
            endSession(playerName, "staff_quit");
        }

        for (Map.Entry<String, SpectatorSession> entry : activeSessions.entrySet()) {
            if (entry.getValue().getTargetName().equals(playerName)) {
                endSession(entry.getKey(), "target_quit");
            }
        }
    }

    public void endAllSessions() {
        for (String staffName : activeSessions.keySet().toArray(new String[0])) {
            endSession(staffName, "plugin_disable");
        }
    }
}
