package dev.hjjang.coraspectator;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

public class SessionLogger {
    private final File logFile;
    private static final DateTimeFormatter TIMESTAMP_FORMAT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    public SessionLogger(File dataFolder) {
        File logDir = new File(dataFolder, "");
        if (!logDir.exists()) {
            logDir.mkdirs();
        }
        this.logFile = new File(logDir, "sessions.log");
    }

    public void logStart(String staff, String target, int duration) {
        String timestamp = getCurrentTimestamp();
        String line = String.format("[%s] START | staff=%s | target=%s | duration=%ds\n",
                timestamp, staff, target, duration);
        writeToLog(line);
    }

    public void logEnd(String staff, String target, String reason) {
        String timestamp = getCurrentTimestamp();
        String line = String.format("[%s] END | staff=%s | target=%s | reason=%s\n",
                timestamp, staff, target, reason);
        writeToLog(line);
    }

    public void logTimeout(String staff, String target) {
        String timestamp = getCurrentTimestamp();
        String line = String.format("[%s] TIMEOUT | staff=%s | target=%s\n",
                timestamp, staff, target);
        writeToLog(line);
    }

    public void logError(String staff, String target, String error) {
        String timestamp = getCurrentTimestamp();
        String line = String.format("[%s] ERROR | staff=%s | target=%s | error=%s\n",
                timestamp, staff, target, error);
        writeToLog(line);
    }

    private String getCurrentTimestamp() {
        return LocalDateTime.now().format(TIMESTAMP_FORMAT);
    }

    private void writeToLog(String line) {
        try (PrintWriter writer = new PrintWriter(new FileWriter(logFile, true))) {
            writer.print(line);
        } catch (IOException e) {
            System.err.println("Failed to write to session log: " + e.getMessage());
        }
    }
}
