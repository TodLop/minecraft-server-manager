package dev.hjjang.moneyhistory.monitor;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class PlayerContext {
    private final List<CommandRecord> recentCommands;
    private final int memoryDurationMs;

    public PlayerContext(int memoryDurationSeconds) {
        this.recentCommands = new ArrayList<>();
        this.memoryDurationMs = memoryDurationSeconds * 1000;
    }

    public void recordCommand(String command) {
        synchronized (recentCommands) {
            recentCommands.add(new CommandRecord(command, System.currentTimeMillis()));
            cleanExpired();
        }
    }

    public List<CommandRecord> getRecentCommands() {
        synchronized (recentCommands) {
            cleanExpired();
            return new ArrayList<>(recentCommands);
        }
    }

    public boolean hasRecentCommand(String prefix, long withinMs) {
        long cutoff = System.currentTimeMillis() - withinMs;
        synchronized (recentCommands) {
            for (CommandRecord record : recentCommands) {
                if (record.timestamp >= cutoff && record.command.toLowerCase().startsWith(prefix.toLowerCase())) {
                    return true;
                }
            }
        }
        return false;
    }

    private void cleanExpired() {
        long cutoff = System.currentTimeMillis() - memoryDurationMs;
        synchronized (recentCommands) {
            Iterator<CommandRecord> iterator = recentCommands.iterator();
            while (iterator.hasNext()) {
                if (iterator.next().timestamp < cutoff) {
                    iterator.remove();
                }
            }
        }
    }

    public static class CommandRecord {
        public final String command;
        public final long timestamp;

        public CommandRecord(String command, long timestamp) {
            this.command = command;
            this.timestamp = timestamp;
        }
    }
}
