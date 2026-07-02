#!/usr/bin/env python3
"""
服务健康检查脚本
scripts/health_check.py

检查所有服务的运行状态
"""

import sys
import asyncio
from typing import Dict, List, Tuple

import httpx


# 服务配置
SERVICES = {
    "MCP服务": [
        ("Weather MCP", "http://localhost:8000/mcp", "MCP"),
        ("Ticket MCP", "http://localhost:8001/mcp", "MCP"),
        ("Order MCP", "http://localhost:8002/mcp", "MCP"),
    ],
    "Agent服务": [
        ("Weather Agent", "http://localhost:5005/.well-known/agent.json", "A2A"),
        ("Ticket Agent", "http://localhost:5006/.well-known/agent.json", "A2A"),
        ("Order Agent", "http://localhost:5007/.well-known/agent.json", "A2A"),
    ],
    "Web服务": [
        ("Streamlit", "http://localhost:8501", "HTTP"),
    ]
}


async def check_service(name: str, url: str, service_type: str) -> Tuple[str, bool, str]:
    """
    检查单个服务

    Args:
        name: 服务名称
        url: 服务URL
        service_type: 服务类型

    Returns:
        (服务名, 是否正常, 详情)
    """
    try:
        # trust_env=False: 本机探活不走系统代理
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.get(url)

            # MCP streamable-http 端点对 GET 返回 4xx 属正常（协议要求 POST），能响应即视为存活
            if service_type == "MCP":
                if response.status_code < 500:
                    return name, True, "OK"
                return name, False, f"HTTP {response.status_code}"

            if response.status_code == 200:
                if service_type == "A2A":
                    try:
                        card = response.json()
                        version = card.get("version", "unknown")
                        return name, True, f"v{version}"
                    except Exception:
                        return name, True, "OK"
                return name, True, "OK"
            return name, False, f"HTTP {response.status_code}"

    except httpx.ConnectError:
        return name, False, "连接失败"
    except httpx.TimeoutException:
        return name, False, "超时"
    except Exception as e:
        return name, False, str(e)


async def check_all_services() -> Dict[str, List[Tuple[str, bool, str]]]:
    """检查所有服务"""
    results = {}

    for category, services in SERVICES.items():
        tasks = [check_service(name, url, stype) for name, url, stype in services]
        category_results = await asyncio.gather(*tasks)
        results[category] = list(category_results)

    return results


def print_results(results: Dict[str, List[Tuple[str, bool, str]]]):
    """打印检查结果"""
    print("=" * 60)
    print("🏥 SmartVoyage 服务健康检查")
    print("=" * 60)

    all_healthy = True

    for category, services in results.items():
        print(f"\n📦 {category}")
        print("-" * 40)

        for name, is_healthy, detail in services:
            if is_healthy:
                status = "✅"
                color_detail = f"\033[92m{detail}\033[0m"  # 绿色
            else:
                status = "❌"
                color_detail = f"\033[91m{detail}\033[0m"  # 红色
                all_healthy = False

            print(f"  {status} {name:<20} {color_detail}")

    print("\n" + "=" * 60)

    if all_healthy:
        print("✅ 所有服务运行正常")
    else:
        print("⚠️ 部分服务异常，请检查")

    print("=" * 60)

    return all_healthy


async def check_database() -> bool:
    """检查数据库连接（SQLite / MySQL 均支持）"""
    try:
        from src.config import config
        from src.mcp_servers.base_service import DatabaseService

        db = DatabaseService()
        db.execute_query("SELECT 1 AS ok")
        db.close()
        print(f"  数据库: {config.database.describe}")
        return True
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return False


def main():
    """主函数"""
    print("\n正在检查服务状态...\n")

    # 检查数据库
    print("📊 检查数据库连接...")
    db_ok = asyncio.run(check_database())
    if db_ok:
        print("  ✅ 数据库连接正常\n")
    else:
        print("  ❌ 数据库连接失败\n")

    # 检查服务
    results = asyncio.run(check_all_services())
    all_healthy = print_results(results)

    # 返回状态码
    sys.exit(0 if (all_healthy and db_ok) else 1)


if __name__ == "__main__":
    main()
