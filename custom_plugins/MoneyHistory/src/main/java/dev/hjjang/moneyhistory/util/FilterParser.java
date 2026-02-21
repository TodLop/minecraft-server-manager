package dev.hjjang.moneyhistory.util;

import dev.hjjang.moneyhistory.model.Source;
import dev.hjjang.moneyhistory.query.HistoryFilters;

import java.util.HashSet;
import java.util.Set;

public class FilterParser {
    public static HistoryFilters parseFilters(String[] args) {
        HistoryFilters.Builder builder = HistoryFilters.builder();

        for (String arg : args) {
            if (!arg.startsWith("--")) {
                continue;
            }

            String[] parts = arg.substring(2).split("=", 2);
            if (parts.length != 2) {
                continue;
            }

            String key = parts[0].toLowerCase();
            String value = parts[1];

            try {
                switch (key) {
                    case "source":
                        Set<Source> sources = parseSources(value);
                        if (!sources.isEmpty()) {
                            builder.sources(sources);
                        }
                        break;

                    case "since":
                        Long sinceMs = TimeFormatter.parseTimeString(value);
                        if (sinceMs != null) {
                            builder.since(sinceMs);
                        }
                        break;

                    case "before":
                        Long beforeMs = TimeFormatter.parseTimeString(value);
                        if (beforeMs != null) {
                            builder.before(beforeMs);
                        }
                        break;

                    case "min":
                        double minDelta = Double.parseDouble(value);
                        builder.minDelta(minDelta);
                        break;

                    case "max":
                        double maxDelta = Double.parseDouble(value);
                        builder.maxDelta(maxDelta);
                        break;
                }
            } catch (Exception e) {
                // Silently ignore invalid filter values
            }
        }

        return builder.build();
    }

    private static Set<Source> parseSources(String value) {
        Set<Source> sources = new HashSet<>();
        String[] parts = value.split(",");

        for (String part : parts) {
            try {
                Source source = Source.valueOf(part.trim().toUpperCase());
                sources.add(source);
            } catch (IllegalArgumentException e) {
                // Invalid source, skip it
            }
        }

        return sources;
    }

    public static boolean hasFilterArgs(String[] args) {
        for (String arg : args) {
            if (arg.startsWith("--")) {
                return true;
            }
        }
        return false;
    }
}
