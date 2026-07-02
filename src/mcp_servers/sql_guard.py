#!/usr/bin/env python3
"""
Text2SQL 安全防线
src/mcp_servers/sql_guard.py

LLM 生成的 SQL 一律经过本层校验后才允许执行：
1. 仅允许单条 SELECT（sqlparse 语法级判定）
2. 禁止注释 / 多语句 / 写操作关键字（正则）
3. 表名白名单
4. 强制 LIMIT 上限
"""

import re
from typing import Iterable, Set

import sqlparse
from sqlparse.tokens import DML


class SQLGuardError(ValueError):
    """SQL 校验失败"""


# 写操作与危险关键字（词边界匹配）
_FORBIDDEN_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|grant|revoke|"
    r"exec|execute|call|merge|handler|load|outfile|dumpfile|infile|"
    r"information_schema|sleep|benchmark|union)\b",
    re.IGNORECASE,
)

# 注释标记
_COMMENT_PATTERN = re.compile(r"(--|/\*|\*/|#)")

_DEFAULT_MAX_LIMIT = 50


def _extract_tables(sql: str) -> Set[str]:
    """提取 FROM/JOIN 后的表名（含子查询中的引用）"""
    tables: Set[str] = set()
    for match in re.finditer(
        r"\b(?:from|join)\s+([`\"\[]?\w+[`\"\]]?)", sql, re.IGNORECASE
    ):
        tables.add(match.group(1).strip('`"[]').lower())
    return tables


def validate_select(
    sql: str,
    allowed_tables: Iterable[str],
    max_limit: int = _DEFAULT_MAX_LIMIT,
) -> str:
    """
    校验并规范化一条 Text2SQL 生成的查询

    Args:
        sql: 待校验 SQL
        allowed_tables: 本服务允许访问的表名白名单
        max_limit: 允许的最大返回行数（缺省时自动追加 LIMIT）

    Returns:
        校验通过、带 LIMIT 的 SQL

    Raises:
        SQLGuardError: 任一防线未通过
    """
    if not sql or not sql.strip():
        raise SQLGuardError("SQL 为空")

    sql = sql.strip().rstrip(";").strip()

    if ";" in sql:
        raise SQLGuardError("禁止多语句执行")

    if _COMMENT_PATTERN.search(sql):
        raise SQLGuardError("禁止 SQL 注释")

    if _FORBIDDEN_PATTERN.search(sql):
        raise SQLGuardError("包含被禁止的关键字，仅允许只读查询")

    statements = [s for s in sqlparse.parse(sql) if str(s).strip()]
    if len(statements) != 1:
        raise SQLGuardError("必须是单条语句")

    statement = statements[0]
    if statement.get_type() != "SELECT":
        raise SQLGuardError("仅允许 SELECT 语句")

    # 首个 DML token 必须是 SELECT（防御 sqlparse 类型误判）
    first_dml = next(
        (t for t in statement.flatten() if t.ttype is DML), None
    )
    if first_dml is None or first_dml.value.upper() != "SELECT":
        raise SQLGuardError("仅允许 SELECT 语句")

    allowed = {t.lower() for t in allowed_tables}
    tables = _extract_tables(sql)
    if not tables:
        raise SQLGuardError("无法解析目标表")
    illegal = tables - allowed
    if illegal:
        raise SQLGuardError(f"禁止访问表: {', '.join(sorted(illegal))}")

    # 强制 LIMIT：无 LIMIT 追加，超上限收紧
    limit_match = re.search(r"\blimit\s+(\d+)", sql, re.IGNORECASE)
    if limit_match:
        if int(limit_match.group(1)) > max_limit:
            sql = re.sub(
                r"\blimit\s+\d+", f"LIMIT {max_limit}", sql, flags=re.IGNORECASE
            )
    else:
        sql = f"{sql} LIMIT {max_limit}"

    return sql
