package dev.hjjang.coraspectator;

import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.inventory.ItemStack;

public class SpectatorSession {
    private final String staffName;
    private final String targetName;
    private final Location originalLocation;
    private final GameMode originalGameMode;
    private final ItemStack[] originalInventory;
    private final ItemStack[] originalArmorContents;
    private final double originalHealth;
    private final int originalFoodLevel;
    private final float originalSaturation;
    private final long startTime;
    private final int durationSeconds;

    public SpectatorSession(String staffName, String targetName, Location originalLocation,
                           GameMode originalGameMode, ItemStack[] originalInventory,
                           ItemStack[] originalArmorContents, double originalHealth,
                           int originalFoodLevel, float originalSaturation, int durationSeconds) {
        this.staffName = staffName;
        this.targetName = targetName;
        this.originalLocation = originalLocation;
        this.originalGameMode = originalGameMode;
        this.originalInventory = originalInventory;
        this.originalArmorContents = originalArmorContents;
        this.originalHealth = originalHealth;
        this.originalFoodLevel = originalFoodLevel;
        this.originalSaturation = originalSaturation;
        this.durationSeconds = durationSeconds;
        this.startTime = System.currentTimeMillis();
    }

    public String getStaffName() {
        return staffName;
    }

    public String getTargetName() {
        return targetName;
    }

    public Location getOriginalLocation() {
        return originalLocation;
    }

    public GameMode getOriginalGameMode() {
        return originalGameMode;
    }

    public ItemStack[] getOriginalInventory() {
        return originalInventory;
    }

    public ItemStack[] getOriginalArmorContents() {
        return originalArmorContents;
    }

    public double getOriginalHealth() {
        return originalHealth;
    }

    public int getOriginalFoodLevel() {
        return originalFoodLevel;
    }

    public float getOriginalSaturation() {
        return originalSaturation;
    }

    public long getStartTime() {
        return startTime;
    }

    public int getDurationSeconds() {
        return durationSeconds;
    }

    public boolean isExpired() {
        long elapsedMillis = System.currentTimeMillis() - startTime;
        return elapsedMillis >= (durationSeconds * 1000L);
    }

    public int getRemainingSeconds() {
        long elapsedMillis = System.currentTimeMillis() - startTime;
        long remainingMillis = (durationSeconds * 1000L) - elapsedMillis;
        return Math.max(0, (int) (remainingMillis / 1000));
    }
}
