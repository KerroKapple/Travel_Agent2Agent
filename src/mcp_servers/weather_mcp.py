#!/usr/bin/env python3
"""
天气MCP服务
src/mcp_servers/weather_mcp.py

提供天气数据查询的MCP服务
"""

from mcp.server.fastmcp import FastMCP

from src.mcp_servers.base_service import DatabaseService
from src.config import config, logger


# 创建MCP服务实例
mcp = FastMCP("WeatherMCP")


class WeatherService(DatabaseService):
    """天气数据服务"""

    ALLOWED_TABLES = {"weather_data"}

    def query_weather(self, sql: str) -> str:
        """
        查询天气数据（LLM 生成的 SQL，经安全层校验后执行）

        Args:
            sql: SQL查询语句

        Returns:
            JSON格式的天气数据
        """
        logger.info(f"天气查询SQL: {sql}")
        return self.execute_select(sql, self.ALLOWED_TABLES)


# 创建服务实例
weather_service = WeatherService()


@mcp.tool()
def query_weather(sql: str) -> str:
    """
    查询天气数据

    Args:
        sql: SQL查询语句，用于查询weather_data表

    Returns:
        JSON格式的天气数据，包含城市、日期、温度、天气描述等
    """
    return weather_service.query_weather(sql)


def main():
    """启动天气MCP服务"""
    import uvicorn

    print("=" * 60)
    print("🌤️ 天气 MCP 服务")
    print("=" * 60)
    print(f"服务地址: http://localhost:{config.mcp.weather_port}")
    print(f"数据库:   {config.database.describe}")
    if config.mock_data:
        print("数据来源: 本地 mock 数据（随机生成），未接入真实天气 API")
    print("=" * 60)

    # 使用streamable_http方式运行
    uvicorn.run(
        mcp.streamable_http_app(),
        host="0.0.0.0",
        port=config.mcp.weather_port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
