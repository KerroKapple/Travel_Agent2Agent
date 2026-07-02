#!/usr/bin/env python3
"""
A2A + MCP 全链路联调 Demo（模拟 LLM，不需要 API Key / MySQL / 外网）
scripts/demo_a2a_e2e.py

链路：A2A 客户端 -> WeatherQueryAgent(A2A 服务) -> 天气 MCP(streamable-http)
      -> SQL 安全层 -> SQLite -> 格式化结果原路返回
运行：uv run python -m scripts.demo_a2a_e2e
前置：uv run python -m scripts.init_data （或先跑过 demo_offline）
"""

import asyncio
import socket
import threading
import time
from datetime import datetime, timedelta

import uvicorn
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.config import config

MCP_PORT = config.mcp.weather_port
AGENT_PORT = config.agents.weather_port


def wait_port(port: int, timeout: float = 15.0):
    """等待端口就绪"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"端口 {port} 未就绪")


def start_weather_mcp():
    """线程内启动天气 MCP（uvicorn）"""
    from src.mcp_servers.weather_mcp import mcp

    server = uvicorn.Server(uvicorn.Config(
        mcp.streamable_http_app(), host="127.0.0.1", port=MCP_PORT, log_level="warning"
    ))
    threading.Thread(target=server.run, daemon=True).start()
    wait_port(MCP_PORT)
    print(f"[启动] 天气 MCP: http://127.0.0.1:{MCP_PORT}/mcp")


def start_weather_agent(fake_sql: str):
    """线程内启动天气 A2A Agent，注入模拟 LLM（固定返回一条 SQL）"""
    from python_a2a import run_server
    from src.agents.weather_agent import WeatherQueryAgent

    agent = WeatherQueryAgent()
    # 模拟 LLM：任何输入都返回同一条 SQL，验证链路本身
    agent.llm = RunnableLambda(lambda _: AIMessage(content=fake_sql))

    threading.Thread(
        target=run_server,
        args=(agent,),
        kwargs={"host": "127.0.0.1", "port": AGENT_PORT},
        daemon=True,
    ).start()
    wait_port(AGENT_PORT)
    print(f"[启动] 天气 A2A Agent: http://127.0.0.1:{AGENT_PORT}")


async def run_client() -> str:
    """A2A 客户端发送任务（与 src/main.py 相同的调用方式）"""
    import uuid
    from python_a2a import A2AClient, Task

    client = A2AClient(f"http://127.0.0.1:{AGENT_PORT}", timeout=30)
    task = Task(
        id=f"task-{uuid.uuid4()}",
        message={"role": "user", "content": {"type": "text", "text": "北京明天天气怎么样"}},
    )
    result = await client.send_task_async(task)

    print(f"[A2A响应] 状态: {result.status.state}")
    if result.artifacts:
        return result.artifacts[0]["parts"][0]["text"]
    message = result.status.message or {}
    content = message.get("content", {})
    return content.get("text", "") if isinstance(content, dict) else str(content)


def main():
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    fake_sql = (
        "SELECT city, fx_date, temp_max, temp_min, text_day, text_night, humidity, "
        "wind_dir_day, wind_scale_day, precip, uv_index "
        f"FROM weather_data WHERE city = '北京' AND fx_date = '{tomorrow}'"
    )

    print("=" * 60)
    print("SmartVoyage A2A+MCP 全链路联调（模拟 LLM）")
    print(f"数据库: {config.database.describe}")
    print("=" * 60)

    start_weather_mcp()
    start_weather_agent(fake_sql)

    text = asyncio.run(run_client())
    print("\n[最终结果]")
    print(text)

    assert "北京" in text and "温度" in text, "未取得预期的天气格式化结果"
    print("\n" + "=" * 60)
    print("✅ A2A + MCP + SQL安全层 + SQLite 全链路验证通过")
    print("=" * 60)


if __name__ == "__main__":
    main()
