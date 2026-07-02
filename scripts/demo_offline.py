#!/usr/bin/env python3
"""
离线端到端 Demo（不需要 LLM Key / MySQL / 网络）
scripts/demo_offline.py

覆盖链路：mock 数据初始化 -> SQL 安全防线 -> 天气/票务查询 -> 下单/查单/取消
运行：uv run python -m scripts.demo_offline
"""

import json
from datetime import datetime, timedelta

from scripts.init_data import main as init_data_main
from src.config import config
from src.mcp_servers.base_service import DatabaseService
from src.mcp_servers.sql_guard import SQLGuardError, validate_select


def step(title: str):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def demo_sql_guard():
    step("① SQL 安全防线演示（Text2SQL 必经之路）")

    ok_sql = "SELECT city, fx_date, temp_max FROM weather_data WHERE city = '北京'"
    print(f"[合法] {ok_sql}")
    print(f"  -> 放行并强制 LIMIT: {validate_select(ok_sql, {'weather_data'})}")

    attacks = [
        "SELECT * FROM weather_data; DROP TABLE orders",
        "SELECT * FROM orders",
        "UPDATE weather_data SET temp_max = 100",
        "SELECT * FROM weather_data WHERE city = '' UNION SELECT contact_phone FROM orders --",
    ]
    for sql in attacks:
        try:
            validate_select(sql, {"weather_data"})
            raise AssertionError(f"漏网之鱼: {sql}")
        except SQLGuardError as e:
            print(f"[拦截] {sql}")
            print(f"  -> {e}")


def demo_queries(db: DatabaseService):
    step("② 模拟 LLM 生成 SQL 的查询链路（天气 / 火车票）")

    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    weather_sql = (
        "SELECT city, fx_date, temp_max, temp_min, text_day, text_night, humidity "
        f"FROM weather_data WHERE city = '北京' AND fx_date = '{tomorrow}'"
    )
    print(f"[天气SQL] {weather_sql}")
    result = json.loads(db.execute_select(weather_sql, {"weather_data"}))
    assert result["status"] == "success", result
    print(f"  -> {result['data'][0]}")

    train_sql = (
        "SELECT id, train_number, seat_type, departure_time, price, remaining_seats "
        "FROM train_tickets WHERE departure_city = '北京' AND arrival_city = '上海' "
        f"AND DATE(departure_time) = '{tomorrow}' AND remaining_seats > 0 "
        "ORDER BY departure_time LIMIT 3"
    )
    print(f"[火车票SQL] {train_sql}")
    result = json.loads(db.execute_select(train_sql, {"train_tickets"}))
    assert result["status"] == "success", result
    for row in result["data"]:
        print(f"  -> 票务ID {row['id']}: {row['train_number']} {row['seat_type']} "
              f"{row['departure_time']} ¥{row['price']} 余{row['remaining_seats']}")
    return result["data"][0]["id"]


def demo_order(ticket_id: int):
    step("③ 订单生命周期（创建 -> 查询 -> 取消）")

    # 延迟导入：模块加载时会创建服务实例并连接数据库
    from src.mcp_servers.order_mcp import order_service

    created = order_service.create_order(
        ticket_type="train",
        ticket_id=ticket_id,
        quantity=1,
        contact_name="张三",
        contact_phone="13800138000",
    )
    assert created["status"] == "success", created
    order_no = created["data"]["order_no"]
    print(f"[创建] 订单号 {order_no}, 总价 ¥{created['data']['total_price']}")

    queried = json.loads(order_service.query_order(order_no))
    assert queried["status"] == "success", queried
    print(f"[查询] 状态: {queried['data'][0]['status']}")

    cancelled = order_service.cancel_order(order_no)
    assert cancelled["status"] == "success", cancelled
    print(f"[取消] {cancelled['message']}")

    after = json.loads(order_service.query_order(order_no))
    print(f"[复查] 状态: {after['data'][0]['status']}")
    assert after["data"][0]["status"] == "cancelled"


def main():
    print("SmartVoyage 离线端到端 Demo")
    print(f"数据库: {config.database.describe}")
    print("说明: 数据均为随机 mock；本 demo 不调用 LLM，SQL 为手写样例，")
    print("      与 LLM 生成的 SQL 走完全相同的校验与执行链路。")

    if config.database.backend != "sqlite":
        print("提示: 当前为 MySQL 后端，离线 demo 建议使用默认 SQLite (DB_BACKEND=sqlite)")

    init_data_main()

    db = DatabaseService()
    try:
        demo_sql_guard()
        ticket_id = demo_queries(db)
        demo_order(ticket_id)
    finally:
        db.close()

    step("✅ 离线 Demo 全部通过")


if __name__ == "__main__":
    main()
