package dev.hjjang.moneyhistory.query;

import dev.hjjang.moneyhistory.model.Source;

import java.util.Set;

public class HistoryFilters {
    private final Long sinceMs;
    private final Long beforeMs;
    private final Set<Source> sources;
    private final Double minDelta;
    private final Double maxDelta;

    private HistoryFilters(Builder builder) {
        this.sinceMs = builder.sinceMs;
        this.beforeMs = builder.beforeMs;
        this.sources = builder.sources;
        this.minDelta = builder.minDelta;
        this.maxDelta = builder.maxDelta;
    }

    public Long getSinceMs() {
        return sinceMs;
    }

    public Long getBeforeMs() {
        return beforeMs;
    }

    public Set<Source> getSources() {
        return sources;
    }

    public Double getMinDelta() {
        return minDelta;
    }

    public Double getMaxDelta() {
        return maxDelta;
    }

    public boolean hasFilters() {
        return sinceMs != null || beforeMs != null || sources != null ||
               minDelta != null || maxDelta != null;
    }

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private Long sinceMs;
        private Long beforeMs;
        private Set<Source> sources;
        private Double minDelta;
        private Double maxDelta;

        public Builder since(long timestampMs) {
            this.sinceMs = timestampMs;
            return this;
        }

        public Builder before(long timestampMs) {
            this.beforeMs = timestampMs;
            return this;
        }

        public Builder sources(Set<Source> sources) {
            this.sources = sources;
            return this;
        }

        public Builder minDelta(double minDelta) {
            this.minDelta = minDelta;
            return this;
        }

        public Builder maxDelta(double maxDelta) {
            this.maxDelta = maxDelta;
            return this;
        }

        public HistoryFilters build() {
            return new HistoryFilters(this);
        }
    }
}
