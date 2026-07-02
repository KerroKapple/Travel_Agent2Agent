#!/usr/bin/env python3
"""
SQL 安全防线单元测试
tests/test_sql_guard.py
"""

import pytest

from src.mcp_servers.sql_guard import SQLGuardError, validate_select

TABLES = {"weather_data", "train_tickets"}


class TestValidateSelect:
    """合法查询"""

    def test_simple_select(self):
        sql = "SELECT city, temp_max FROM weather_data WHERE city = '北京'"
        result = validate_select(sql, TABLES)
        assert result.endswith("LIMIT 50")

    def test_keeps_small_limit(self):
        sql = "SELECT * FROM train_tickets LIMIT 10"
        assert "LIMIT 10" in validate_select(sql, TABLES)

    def test_shrinks_large_limit(self):
        sql = "SELECT * FROM train_tickets LIMIT 99999"
        assert "LIMIT 50" in validate_select(sql, TABLES)

    def test_strips_trailing_semicolon(self):
        sql = "SELECT city FROM weather_data;"
        assert ";" not in validate_select(sql, TABLES)

    def test_column_named_like_keyword_ok(self):
        # created_at 不应触发 create 关键字拦截
        sql = "SELECT created_at FROM train_tickets"
        validate_select(sql, TABLES)


class TestBlocked:
    """必须拦截"""

    def test_empty(self):
        with pytest.raises(SQLGuardError):
            validate_select("", TABLES)

    def test_multi_statement(self):
        with pytest.raises(SQLGuardError, match="多语句"):
            validate_select("SELECT 1 FROM weather_data; DROP TABLE orders", TABLES)

    def test_comment_injection(self):
        with pytest.raises(SQLGuardError, match="注释"):
            validate_select("SELECT * FROM weather_data -- x", TABLES)

    def test_update(self):
        with pytest.raises(SQLGuardError):
            validate_select("UPDATE weather_data SET temp_max = 1", TABLES)

    def test_delete(self):
        with pytest.raises(SQLGuardError):
            validate_select("DELETE FROM weather_data", TABLES)

    def test_drop(self):
        with pytest.raises(SQLGuardError):
            validate_select("DROP TABLE weather_data", TABLES)

    def test_insert(self):
        with pytest.raises(SQLGuardError):
            validate_select("INSERT INTO weather_data VALUES (1)", TABLES)

    def test_union_exfiltration(self):
        with pytest.raises(SQLGuardError):
            validate_select(
                "SELECT city FROM weather_data UNION SELECT contact_phone FROM orders",
                TABLES,
            )

    def test_table_not_in_whitelist(self):
        with pytest.raises(SQLGuardError, match="禁止访问表"):
            validate_select("SELECT * FROM orders", TABLES)

    def test_subquery_hits_forbidden_table(self):
        with pytest.raises(SQLGuardError, match="禁止访问表"):
            validate_select(
                "SELECT * FROM weather_data WHERE city IN (SELECT city FROM secret)",
                TABLES,
            )

    def test_sleep_function(self):
        with pytest.raises(SQLGuardError):
            validate_select("SELECT SLEEP(10) FROM weather_data", TABLES)

    def test_information_schema(self):
        with pytest.raises(SQLGuardError):
            validate_select("SELECT * FROM information_schema.tables", TABLES)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
