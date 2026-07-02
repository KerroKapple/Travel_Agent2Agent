#!/usr/bin/env python3
"""
MCP 数据服务基类
src/mcp_servers/base_service.py

双后端数据访问层：SQLite（默认，零外部依赖）/ MySQL
- 内部查询一律参数化（占位符统一写 %s，SQLite 自动转 ?）
- LLM 生成的 SQL 必须走 execute_select，经 sql_guard 校验
"""

import json
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.config import config, logger
from src.mcp_servers.sql_guard import SQLGuardError, validate_select


class DateTimeEncoder(json.JSONEncoder):
    """处理日期时间/Decimal 的 JSON 编码器"""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        if isinstance(obj, timedelta):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class DatabaseService:
    """数据库服务基类（SQLite / MySQL 双后端）"""

    def __init__(self):
        self.backend = config.database.backend
        self._conn = None
        self._connect()

    # ---------- 连接管理 ----------

    def _connect(self):
        if self.backend == "sqlite":
            path = config.database.sqlite_path
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            logger.info(f"SQLite 连接成功: {path}")
        else:
            import mysql.connector  # 仅 MySQL 后端需要
            self._conn = mysql.connector.connect(**config.database.mysql_params)
            logger.info(f"MySQL 连接成功: {config.database.describe}")

    def _ensure_connection(self):
        if self.backend == "sqlite":
            if self._conn is None:
                self._connect()
            return
        try:
            if self._conn is None or not self._conn.is_connected():
                self._connect()
        except Exception:
            self._connect()

    def _adapt(self, sql: str, params: Optional[tuple]) -> tuple:
        """占位符适配：SQLite 使用 ?，MySQL 使用 %s"""
        if self.backend == "sqlite" and params:
            sql = sql.replace("%s", "?")
        return sql, params or ()

    # ---------- 查询 ----------

    def _fetch_all(self, sql: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        self._ensure_connection()
        sql, params = self._adapt(sql, params)

        if self.backend == "sqlite":
            cursor = self._conn.execute(sql, params)
            rows = [dict(r) for r in cursor.fetchall()]
            cursor.close()
        else:
            cursor = self._conn.cursor(dictionary=True)
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            cursor.close()

        for row in rows:
            for key, value in row.items():
                row[key] = self._encode_value(value)
        return rows

    def execute_select(self, sql: str, allowed_tables) -> str:
        """
        执行 Text2SQL 生成的查询（唯一允许原样 SQL 的入口）

        经 sql_guard 校验：单条 SELECT + 表白名单 + 强制 LIMIT
        """
        try:
            safe_sql = validate_select(sql, allowed_tables)
        except SQLGuardError as e:
            logger.warning(f"SQL 被安全层拦截: {e} | SQL: {sql}")
            return json.dumps(
                {"status": "error", "message": f"SQL 校验失败: {e}"},
                ensure_ascii=False
            )

        try:
            rows = self._fetch_all(safe_sql)
        except Exception as e:
            logger.error(f"SQL执行错误: {e}")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

        if rows:
            return json.dumps(
                {"status": "success", "data": rows},
                cls=DateTimeEncoder, ensure_ascii=False
            )
        return json.dumps({"status": "no_data", "message": "未找到数据"}, ensure_ascii=False)

    def execute_query(self, sql: str, params: Optional[tuple] = None) -> str:
        """执行内部参数化查询，返回 JSON"""
        try:
            rows = self._fetch_all(sql, params)
        except Exception as e:
            logger.error(f"SQL执行错误: {e}")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

        if rows:
            return json.dumps(
                {"status": "success", "data": rows},
                cls=DateTimeEncoder, ensure_ascii=False
            )
        return json.dumps({"status": "no_data", "message": "未找到数据"}, ensure_ascii=False)

    # ---------- 写入 ----------

    def execute_insert(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        self._ensure_connection()
        sql, params = self._adapt(sql, params)

        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, params)
            self._conn.commit()
            last_id = cursor.lastrowid
            cursor.close()
            return {"status": "success", "id": last_id}
        except Exception as e:
            logger.error(f"INSERT执行错误: {e}")
            self._conn.rollback()
            return {"status": "error", "message": str(e)}

    def execute_update(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        self._ensure_connection()
        sql, params = self._adapt(sql, params)

        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, params)
            self._conn.commit()
            affected = cursor.rowcount
            cursor.close()
            return {"status": "success", "affected_rows": affected}
        except Exception as e:
            logger.error(f"UPDATE执行错误: {e}")
            self._conn.rollback()
            return {"status": "error", "message": str(e)}

    def execute_script(self, script: str) -> None:
        """执行多语句脚本（建表用，仅 SQLite）"""
        self._ensure_connection()
        if self.backend != "sqlite":
            raise RuntimeError("execute_script 仅支持 SQLite，MySQL 请使用 sql/init_database.sql")
        self._conn.executescript(script)
        self._conn.commit()

    # ---------- 工具 ----------

    def _encode_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(value, date):
            return value.strftime('%Y-%m-%d')
        if isinstance(value, timedelta):
            return str(value)
        if isinstance(value, Decimal):
            return float(value)
        return value

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
                logger.info("数据库连接已关闭")
