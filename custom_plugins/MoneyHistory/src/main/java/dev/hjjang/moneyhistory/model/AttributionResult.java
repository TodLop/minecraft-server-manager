package dev.hjjang.moneyhistory.model;

public class AttributionResult {
    private final Source source;
    private final String details;

    public AttributionResult(Source source, String details) {
        this.source = source;
        this.details = details;
    }

    public AttributionResult(Source source) {
        this(source, null);
    }

    public Source getSource() {
        return source;
    }

    public String getDetails() {
        return details;
    }
}
