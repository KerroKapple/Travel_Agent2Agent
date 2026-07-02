#!/usr/bin/env python3
"""
Mock 数据初始化脚本
scripts/init_data.py

说明：所有数据均为 random 随机生成的演示数据，不来自任何真实 API。
SQLite 后端（默认）自动建表；MySQL 后端需先执行 sql/init_database.sql。
"""

import random
from datetime import datetime, timedelta
from pathlib import Path

from src.config import config
from src.mcp_servers.base_service import DatabaseService

PROJECT_ROOT = Path(__file__).parent.parent


def prepare_schema(db: DatabaseService):
    """SQLite 自动建表；MySQL 假定已执行 init_database.sql"""
    if db.backend == "sqlite":
        script = (PROJECT_ROOT / "sql" / "init_sqlite.sql").read_text(encoding="utf-8")
        db.execute_script(script)
        print(f"  ✅ SQLite 建表完成: {config.database.sqlite_path}")
    else:
        # 清空旧演示数据，保证幂等
        for table in ("weather_data", "train_tickets", "flight_tickets", "concert_tickets"):
            db.execute_update(f"DELETE FROM {table}")
        print("  ✅ MySQL 旧数据已清空（表结构来自 sql/init_database.sql）")


def init_weather_data(db: DatabaseService):
    """随机生成未来30天四城天气"""
    print("📊 初始化天气数据（mock）...")

    cities = ["北京", "上海", "广州", "深圳"]
    weathers = ["晴", "多云", "阴", "小雨", "中雨", "雷阵雨"]
    base_date = datetime.now().date()

    count = 0
    for city in cities:
        temp_base = {"北京": 5, "上海": 10, "广州": 18, "深圳": 20}[city]

        for i in range(30):
            fx_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            temp_min = temp_base + random.randint(-5, 5)
            temp_max = temp_base + random.randint(6, 15)

            db.execute_insert(
                """
                INSERT INTO weather_data (
                    city, fx_date, temp_max, temp_min, text_day, text_night,
                    humidity, wind_dir_day, wind_scale_day, precip, uv_index
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    city, fx_date, temp_max, temp_min,
                    random.choice(weathers), random.choice(weathers),
                    random.randint(30, 90),
                    random.choice(["东风", "西风", "南风", "北风"]),
                    random.choice(["1-2", "3-4", "4-5"]),
                    round(random.uniform(0, 10), 1),
                    random.randint(1, 10),
                ),
            )
            count += 1

    print(f"  ✅ 天气数据: {count} 条")


def init_train_tickets(db: DatabaseService):
    """随机生成未来7天火车票"""
    print("🚄 初始化火车票数据（mock）...")

    routes = [
        ("北京", "上海", ["G101", "G103", "G105"], 270, 553.50, 933.50),
        ("上海", "杭州", ["G7501", "G7503", "G7505"], 50, 73.00, 117.00),
        ("广州", "深圳", ["G6001", "G6003", "G6005"], 45, 79.50, 127.00),
        ("成都", "重庆", ["G8501", "G8503", "G8505"], 100, 65.00, 104.00),
    ]

    times = ["07:00", "09:00", "11:00", "14:00", "16:00", "18:00"]
    base_date = datetime.now()

    count = 0
    for dep, arr, trains, duration, price2, price1 in routes:
        for train in trains:
            for day_offset in range(7):
                for time_str in random.sample(times, 3):
                    hour, minute = map(int, time_str.split(":"))
                    dep_time = (base_date + timedelta(days=day_offset)).replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )
                    arr_time = dep_time + timedelta(minutes=duration)

                    for seat_type, price in [("二等座", price2), ("一等座", price1)]:
                        db.execute_insert(
                            """
                            INSERT INTO train_tickets (
                                departure_city, arrival_city, departure_time, arrival_time,
                                train_number, seat_type, total_seats, remaining_seats, price
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                dep, arr,
                                dep_time.strftime("%Y-%m-%d %H:%M:%S"),
                                arr_time.strftime("%Y-%m-%d %H:%M:%S"),
                                train, seat_type,
                                random.randint(500, 1000), random.randint(50, 500), price,
                            ),
                        )
                        count += 1

    print(f"  ✅ 火车票数据: {count} 条")


def init_flight_tickets(db: DatabaseService):
    """随机生成未来7天机票"""
    print("✈️ 初始化机票数据（mock）...")

    routes = [
        ("北京", "上海", ["CA1001", "MU5101", "CZ3101"], 130, 800, 2000, 4000),
        ("上海", "广州", ["CA1501", "MU5501", "CZ3501"], 150, 900, 2200, 4500),
        ("深圳", "北京", ["CA1801", "MU5801", "CZ3801"], 180, 1000, 2500, 5000),
    ]

    times = ["08:00", "10:00", "13:00", "15:00", "18:00", "20:00"]
    base_date = datetime.now()

    count = 0
    for dep, arr, flights, duration, eco_price, biz_price, first_price in routes:
        for flight in flights:
            for day_offset in range(7):
                for time_str in random.sample(times, 2):
                    hour, minute = map(int, time_str.split(":"))
                    dep_time = (base_date + timedelta(days=day_offset)).replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )
                    arr_time = dep_time + timedelta(minutes=duration)

                    cabins = [
                        ("经济舱", eco_price, 150, 80),
                        ("商务舱", biz_price, 30, 15),
                        ("头等舱", first_price, 8, 4),
                    ]

                    for cabin, price, total, remain in cabins:
                        db.execute_insert(
                            """
                            INSERT INTO flight_tickets (
                                departure_city, arrival_city, departure_time, arrival_time,
                                flight_number, cabin_type, total_seats, remaining_seats, price
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                dep, arr,
                                dep_time.strftime("%Y-%m-%d %H:%M:%S"),
                                arr_time.strftime("%Y-%m-%d %H:%M:%S"),
                                flight, cabin,
                                total, random.randint(1, remain), price,
                            ),
                        )
                        count += 1

    print(f"  ✅ 机票数据: {count} 条")


def init_concert_tickets(db: DatabaseService):
    """随机生成演唱会票"""
    print("🎤 初始化演唱会票数据（mock）...")

    concerts = [
        ("周杰伦", "北京", "国家体育场", 680, 1280, 1880, 3880),
        ("周杰伦", "上海", "梅赛德斯奔驰中心", 680, 1280, 1880, 3880),
        ("五月天", "广州", "天河体育中心", 480, 880, 1580, 2880),
        ("刀郎", "深圳", "深圳湾体育中心", 380, 680, 1280, 2280),
    ]

    base_date = datetime.now()

    count = 0
    for artist, city, venue, p1, p2, p3, p4 in concerts:
        for day_offset in [7, 14, 21]:
            start_time = (base_date + timedelta(days=day_offset)).replace(
                hour=19, minute=30, second=0, microsecond=0
            )
            end_time = start_time + timedelta(hours=3)

            tickets = [
                ("看台票", p1, 5000, 2000),
                ("内场票", p2, 2000, 500),
                ("VIP票", p3, 500, 100),
                ("SVIP票", p4, 100, 20),
            ]

            for ticket_type, price, total, remain in tickets:
                db.execute_insert(
                    """
                    INSERT INTO concert_tickets (
                        artist, city, venue, start_time, end_time,
                        ticket_type, total_seats, remaining_seats, price
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        artist, city, venue,
                        start_time.strftime("%Y-%m-%d %H:%M:%S"),
                        end_time.strftime("%Y-%m-%d %H:%M:%S"),
                        ticket_type, total, random.randint(1, remain), price,
                    ),
                )
                count += 1

    print(f"  ✅ 演唱会票数据: {count} 条")


def main():
    print("=" * 60)
    print("📦 SmartVoyage Mock 数据初始化")
    print(f"数据库: {config.database.describe}")
    print("提示: 以下数据全部随机生成，仅用于演示")
    print("=" * 60)

    db = DatabaseService()

    try:
        prepare_schema(db)
        init_weather_data(db)
        init_train_tickets(db)
        init_flight_tickets(db)
        init_concert_tickets(db)

        print("\n" + "=" * 60)
        print("✅ 数据初始化完成!")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
