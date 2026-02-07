package dev.hjjang.moneyhistory.query;

import dev.hjjang.moneyhistory.model.Source;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class QueryBuilder {
    private final StringBuilder sql;
    private final List<Object> parameters;
    private int parameterIndex;

    public QueryBuilder() {
        this.sql = new StringBuilder();
        this.parameters = new ArrayList<>();
        this.parameterIndex = 1;
    }

    public QueryBuilder select(String columns) {
        sql.append("SELECT ").append(columns);
        return this;
    }

    public QueryBuilder from(String table) {
        sql.append(" FROM ").append(table);
        return this;
    }

    public QueryBuilder where(String condition) {
        if (sql.indexOf(" WHERE ") == -1) {
            sql.append(" WHERE ");
        } else {
            sql.append(" AND ");
        }
        sql.append(condition);
        return this;
    }

    public QueryBuilder orderBy(String column, boolean descending) {
        sql.append(" ORDER BY ").append(column);
        if (descending) {
            sql.append(" DESC");
        }
        return this;
    }

    public QueryBuilder limit(int limit) {
        sql.append(" LIMIT ?");
        parameters.add(limit);
        return this;
    }

    public QueryBuilder offset(int offset) {
        sql.append(" OFFSET ?");
        parameters.add(offset);
        return this;
    }

    public QueryBuilder addParameter(Object value) {
        parameters.add(value);
        return this;
    }

    public String getSql() {
        return sql.toString();
    }

    public PreparedStatement prepareStatement(java.sql.Connection conn) throws SQLException {
        PreparedStatement stmt = conn.prepareStatement(sql.toString());
        for (int i = 0; i < parameters.size(); i++) {
            Object param = parameters.get(i);
            if (param instanceof String) {
                stmt.setString(i + 1, (String) param);
            } else if (param instanceof Integer) {
                stmt.setInt(i + 1, (Integer) param);
            } else if (param instanceof Long) {
                stmt.setLong(i + 1, (Long) param);
            } else if (param instanceof Double) {
                stmt.setDouble(i + 1, (Double) param);
            } else if (param instanceof Boolean) {
                stmt.setBoolean(i + 1, (Boolean) param);
            }
        }
        return stmt;
    }

    public static QueryBuilder buildHistoryQuery(UUID playerUuid, HistoryFilters filters, int page, int entriesPerPage) {
        QueryBuilder builder = new QueryBuilder();

        builder.select("id, player_uuid, player_name, timestamp_ms, balance_before, balance_after, delta, source, details")
               .from("balance_history")
               .where("player_uuid = ?")
               .addParameter(playerUuid.toString());

        // Apply filters
        if (filters != null) {
            if (filters.getSinceMs() != null) {
                builder.where("timestamp_ms >= ?").addParameter(filters.getSinceMs());
            }

            if (filters.getBeforeMs() != null) {
                builder.where("timestamp_ms <= ?").addParameter(filters.getBeforeMs());
            }

            if (filters.getSources() != null && !filters.getSources().isEmpty()) {
                StringBuilder sourceCondition = new StringBuilder("source IN (");
                int count = 0;
                for (Source source : filters.getSources()) {
                    if (count++ > 0) sourceCondition.append(", ");
                    sourceCondition.append("?");
                    builder.addParameter(source.name());
                }
                sourceCondition.append(")");
                builder.where(sourceCondition.toString());
            }

            if (filters.getMinDelta() != null) {
                builder.where("delta >= ?").addParameter(filters.getMinDelta());
            }

            if (filters.getMaxDelta() != null) {
                builder.where("delta <= ?").addParameter(filters.getMaxDelta());
            }
        }

        // Order by timestamp descending (newest first)
        builder.orderBy("timestamp_ms", true);

        // Pagination
        int offset = (page - 1) * entriesPerPage;
        builder.limit(entriesPerPage).offset(offset);

        return builder;
    }

    public static QueryBuilder buildCountQuery(UUID playerUuid, HistoryFilters filters) {
        QueryBuilder builder = new QueryBuilder();

        builder.select("COUNT(*)")
               .from("balance_history")
               .where("player_uuid = ?")
               .addParameter(playerUuid.toString());

        // Apply same filters as history query
        if (filters != null) {
            if (filters.getSinceMs() != null) {
                builder.where("timestamp_ms >= ?").addParameter(filters.getSinceMs());
            }

            if (filters.getBeforeMs() != null) {
                builder.where("timestamp_ms <= ?").addParameter(filters.getBeforeMs());
            }

            if (filters.getSources() != null && !filters.getSources().isEmpty()) {
                StringBuilder sourceCondition = new StringBuilder("source IN (");
                int count = 0;
                for (Source source : filters.getSources()) {
                    if (count++ > 0) sourceCondition.append(", ");
                    sourceCondition.append("?");
                    builder.addParameter(source.name());
                }
                sourceCondition.append(")");
                builder.where(sourceCondition.toString());
            }

            if (filters.getMinDelta() != null) {
                builder.where("delta >= ?").addParameter(filters.getMinDelta());
            }

            if (filters.getMaxDelta() != null) {
                builder.where("delta <= ?").addParameter(filters.getMaxDelta());
            }
        }

        return builder;
    }
}
