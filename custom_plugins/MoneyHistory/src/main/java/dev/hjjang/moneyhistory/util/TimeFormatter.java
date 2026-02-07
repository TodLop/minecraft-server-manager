package dev.hjjang.moneyhistory.util;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TimeFormatter {
    private static final SimpleDateFormat DATE_FORMAT = new SimpleDateFormat("yyyy-MM-dd");
    private static final SimpleDateFormat DATETIME_FORMAT = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
    private static final SimpleDateFormat DISPLAY_FORMAT = new SimpleDateFormat("MMM dd, hh:mm a");

    private static final Pattern DURATION_PATTERN = Pattern.compile("(\\d+)([smhdwy])");

    public static String formatRelative(long timestampMs) {
        long now = System.currentTimeMillis();
        long diff = now - timestampMs;

        if (diff < 0) {
            return "in the future";
        }

        long seconds = TimeUnit.MILLISECONDS.toSeconds(diff);
        long minutes = TimeUnit.MILLISECONDS.toMinutes(diff);
        long hours = TimeUnit.MILLISECONDS.toHours(diff);
        long days = TimeUnit.MILLISECONDS.toDays(diff);

        if (seconds < 60) {
            return seconds + " second" + (seconds != 1 ? "s" : "") + " ago";
        } else if (minutes < 60) {
            return minutes + " minute" + (minutes != 1 ? "s" : "") + " ago";
        } else if (hours < 24) {
            return hours + " hour" + (hours != 1 ? "s" : "") + " ago";
        } else if (days < 30) {
            return days + " day" + (days != 1 ? "s" : "") + " ago";
        } else {
            long months = days / 30;
            return months + " month" + (months != 1 ? "s" : "") + " ago";
        }
    }

    public static String formatAbsolute(long timestampMs) {
        return DATETIME_FORMAT.format(new Date(timestampMs));
    }

    public static String formatDisplay(long timestampMs) {
        return DISPLAY_FORMAT.format(new Date(timestampMs));
    }

    public static Long parseDuration(String input) {
        if (input == null || input.isEmpty()) {
            return null;
        }

        Matcher matcher = DURATION_PATTERN.matcher(input.toLowerCase());
        long totalMs = 0;

        while (matcher.find()) {
            long value = Long.parseLong(matcher.group(1));
            String unit = matcher.group(2);

            switch (unit) {
                case "s":
                    totalMs += TimeUnit.SECONDS.toMillis(value);
                    break;
                case "m":
                    totalMs += TimeUnit.MINUTES.toMillis(value);
                    break;
                case "h":
                    totalMs += TimeUnit.HOURS.toMillis(value);
                    break;
                case "d":
                    totalMs += TimeUnit.DAYS.toMillis(value);
                    break;
                case "w":
                    totalMs += TimeUnit.DAYS.toMillis(value * 7);
                    break;
                case "y":
                    totalMs += TimeUnit.DAYS.toMillis(value * 365);
                    break;
            }
        }

        return totalMs > 0 ? totalMs : null;
    }

    public static Long parseDate(String input) {
        if (input == null || input.isEmpty()) {
            return null;
        }

        try {
            // Try full datetime format first
            Date date = DATETIME_FORMAT.parse(input);
            return date.getTime();
        } catch (Exception e) {
            try {
                // Try date only format
                Date date = DATE_FORMAT.parse(input);
                return date.getTime();
            } catch (Exception ex) {
                return null;
            }
        }
    }

    public static Long parseTimeString(String input) {
        if (input == null || input.isEmpty()) {
            return null;
        }

        // Try duration first (e.g., "7d", "2h")
        Long duration = parseDuration(input);
        if (duration != null) {
            return System.currentTimeMillis() - duration;
        }

        // Try absolute date
        return parseDate(input);
    }
}
