#!/usr/bin/env python3
"""
票务MCP服务
src/mcp_servers/ticket_mcp.py

提供火车票、机票、演唱会票数据查询的MCP服务
"""

from mcp.server.fastmcp import FastMCP

from src.mcp_servers.base_service import DatabaseService
from src.config import config, logger


# 创建MCP服务实例
mcp = FastMCP("TicketMCP")


class TicketService(DatabaseService):
    """票务数据服务"""

    ALLOWED_TABLES = {"train_tickets", "flight_tickets", "concert_tickets"}

    def query_tickets(self, sql: str) -> str:
        """
        查询票务数据（LLM 生成的 SQL，经安全层校验后执行）

        Args:
            sql: SQL查询语句

        Returns:
            JSON格式的票务数据
        """
        logger.info(f"票务查询SQL: {sql}")
        return self.execute_select(sql, self.ALLOWED_TABLES)


# 创建服务实例
ticket_service = TicketService()


@mcp.tool()
def query_tickets(sql: str) -> str:
    """
    查询票务数据

    Args:
        sql: SQL查询语句，可查询train_tickets、flight_tickets、concert_tickets表

    Returns:
        JSON格式的票务数据，包含出发到达信息、时间、价格、余票等
    """
    return ticket_service.query_tickets(sql)


@mcp.tool()
def query_train_tickets(
    departure_city: str,
    arrival_city: str,
    date: str,
    seat_type: str = None
) -> str:
    """
    查询火车票

    Args:
        departure_city: 出发城市
        arrival_city: 到达城市
        date: 出发日期 (YYYY-MM-DD)
        seat_type: 座位类型 (可选: 二等座/一等座/商务座)

    Returns:
        JSON格式的火车票数据
    """
    # 参数化查询，杜绝拼接注入
    sql = """
    SELECT id, departure_city, arrival_city, departure_time, arrival_time,
           train_number, seat_type, price, remaining_seats
    FROM train_tickets
    WHERE departure_city = %s
      AND arrival_city = %s
      AND DATE(departure_time) = %s
      AND remaining_seats > 0
    """
    params = [departure_city, arrival_city, date]
    if seat_type:
        sql += " AND seat_type = %s"
        params.append(seat_type)
    sql += " ORDER BY departure_time LIMIT 20"

    logger.info(f"火车票参数化查询: {params}")
    return ticket_service.execute_query(sql, tuple(params))


@mcp.tool()
def query_flight_tickets(
    departure_city: str,
    arrival_city: str,
    date: str,
    cabin_type: str = None
) -> str:
    """
    查询机票

    Args:
        departure_city: 出发城市
        arrival_city: 到达城市
        date: 出发日期 (YYYY-MM-DD)
        cabin_type: 舱位类型 (可选: 经济舱/商务舱/头等舱)

    Returns:
        JSON格式的机票数据
    """
    # 参数化查询，杜绝拼接注入
    sql = """
    SELECT id, departure_city, arrival_city, departure_time, arrival_time,
           flight_number, cabin_type, price, remaining_seats
    FROM flight_tickets
    WHERE departure_city = %s
      AND arrival_city = %s
      AND DATE(departure_time) = %s
      AND remaining_seats > 0
    """
    params = [departure_city, arrival_city, date]
    if cabin_type:
        sql += " AND cabin_type = %s"
        params.append(cabin_type)
    sql += " ORDER BY departure_time LIMIT 20"

    logger.info(f"机票参数化查询: {params}")
    return ticket_service.execute_query(sql, tuple(params))


@mcp.tool()
def query_concert_tickets(
    city: str = None,
    artist: str = None,
    date: str = None,
    ticket_type: str = None
) -> str:
    """
    查询演唱会票

    Args:
        city: 城市 (可选)
        artist: 艺人名称 (可选)
        date: 演出日期 (可选, YYYY-MM-DD)
        ticket_type: 票类型 (可选: 看台票/内场票/VIP票)

    Returns:
        JSON格式的演唱会票数据
    """
    # 参数化查询，杜绝拼接注入
    conditions = ["remaining_seats > 0"]
    params = []

    if city:
        conditions.append("city = %s")
        params.append(city)
    if artist:
        conditions.append("artist LIKE %s")
        params.append(f"%{artist}%")
    if date:
        conditions.append("DATE(start_time) = %s")
        params.append(date)
    if ticket_type:
        conditions.append("ticket_type = %s")
        params.append(ticket_type)

    sql = f"""
    SELECT id, artist, city, venue, start_time, end_time,
           ticket_type, price, remaining_seats
    FROM concert_tickets
    WHERE {' AND '.join(conditions)}
    ORDER BY start_time LIMIT 20
    """

    logger.info(f"演唱会参数化查询: {params}")
    return ticket_service.execute_query(sql, tuple(params))


def main():
    """启动票务MCP服务"""
    import uvicorn

    print("=" * 60)
    print("🎫 票务 MCP 服务")
    print("=" * 60)
    print(f"服务地址: http://localhost:{config.mcp.ticket_port}")
    print(f"数据库:   {config.database.describe}")
    if config.mock_data:
        print("数据来源: 本地 mock 数据（随机生成），未接入真实票务 API")
    print("=" * 60)
    print("\n可用工具：")
    print("  - query_tickets: 通用SQL查询")
    print("  - query_train_tickets: 查询火车票")
    print("  - query_flight_tickets: 查询机票")
    print("  - query_concert_tickets: 查询演唱会票")
    print("=" * 60)

    uvicorn.run(
        mcp.streamable_http_app(),
        host="0.0.0.0",
        port=config.mcp.ticket_port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
