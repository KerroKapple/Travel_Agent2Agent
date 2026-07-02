#!/usr/bin/env python3
"""
Agent 集成测试（需要服务已启动 + LLM Key）
tests/test_agents.py

运行前置：
  1. uv run python -m scripts.init_data
  2. 启动 3 个 MCP 与 3 个 Agent（见 scripts/start_services.sh）
  3. RUN_INTEGRATION=1 uv run python -m pytest tests/test_agents.py
"""

import os
import uuid
from datetime import datetime, timedelta

import pytest
import httpx

# 默认跳过：这些测试依赖运行中的服务与 LLM Key
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1",
    reason="集成测试需 RUN_INTEGRATION=1 且服务已启动",
)

WEATHER_AGENT_URL = "http://localhost:5005"
TICKET_AGENT_URL = "http://localhost:5006"
ORDER_AGENT_URL = "http://localhost:5007"


async def send_a2a_request(url: str, text: str) -> dict:
    """发送 A2A tasks/send 请求（JSON-RPC，params 为完整 Task）"""
    request_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tasks/send",
        "params": {
            "id": str(uuid.uuid4()),
            "sessionId": str(uuid.uuid4()),
            "message": {
                "role": "user",
                "content": {"type": "text", "text": text},
            },
        },
    }

    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        response = await client.post(
            f"{url}/tasks/send",
            json=request_data,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()


def extract_state(result: dict) -> str:
    """提取任务状态：result.status.state"""
    return result.get("result", {}).get("status", {}).get("state", "")


def extract_content(result: dict) -> str:
    """提取响应文本：完成态在 artifacts，其余在 status.message"""
    task = result.get("result", {})

    artifacts = task.get("artifacts") or []
    if artifacts:
        parts = artifacts[0].get("parts") or []
        if parts:
            return parts[0].get("text", "")

    message = task.get("status", {}).get("message") or {}
    content = message.get("content")
    if isinstance(content, dict):
        return content.get("text", "")
    if isinstance(content, str):
        return content
    # Google A2A 格式兜底
    parts = message.get("parts") or []
    if parts:
        return parts[0].get("text", "")
    return ""


class TestWeatherAgent:
    """测试天气Agent"""

    @pytest.mark.asyncio
    async def test_query_weather_valid(self):
        result = await send_a2a_request(WEATHER_AGENT_URL, "北京明天天气怎么样")

        state = extract_state(result)
        content = extract_content(result)

        assert state in ["completed", "input-required"]
        if state == "completed":
            assert "北京" in content or "天气" in content

    @pytest.mark.asyncio
    async def test_query_weather_missing_city(self):
        result = await send_a2a_request(WEATHER_AGENT_URL, "明天天气")
        assert extract_state(result) == "input-required"

    @pytest.mark.asyncio
    async def test_agent_card(self):
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            response = await client.get(f"{WEATHER_AGENT_URL}/.well-known/agent.json")

        assert response.status_code == 200
        card = response.json()
        assert card.get("name") == "WeatherQueryAgent"
        assert "skills" in card


class TestTicketAgent:
    """测试票务Agent"""

    @pytest.mark.asyncio
    async def test_query_train_ticket(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        result = await send_a2a_request(
            TICKET_AGENT_URL, f"查询{tomorrow}北京到上海的高铁票"
        )
        assert extract_state(result) in ["completed", "input-required"]

    @pytest.mark.asyncio
    async def test_query_flight_ticket(self):
        result = await send_a2a_request(TICKET_AGENT_URL, "明天上海飞广州的机票")
        assert extract_state(result) in ["completed", "input-required"]

    @pytest.mark.asyncio
    async def test_query_concert_ticket(self):
        result = await send_a2a_request(TICKET_AGENT_URL, "周杰伦北京演唱会")
        assert extract_state(result) in ["completed", "input-required"]

    @pytest.mark.asyncio
    async def test_query_missing_info(self):
        result = await send_a2a_request(TICKET_AGENT_URL, "火车票")
        assert extract_state(result) == "input-required"


class TestOrderAgent:
    """测试订票Agent"""

    @pytest.mark.asyncio
    async def test_order_missing_contact(self):
        result = await send_a2a_request(
            ORDER_AGENT_URL, "订一张明天北京到上海的高铁票"
        )

        state = extract_state(result)
        content = extract_content(result)

        assert state == "input-required"
        assert "联系人" in content or "姓名" in content or "电话" in content

    @pytest.mark.asyncio
    async def test_order_with_contact(self):
        result = await send_a2a_request(
            ORDER_AGENT_URL,
            "订一张明天北京到上海的高铁票，二等座，张三，13800138000",
        )
        assert extract_state(result) in ["completed", "input-required", "failed"]

    @pytest.mark.asyncio
    async def test_order_by_ticket_id(self):
        result = await send_a2a_request(
            ORDER_AGENT_URL, "订票务ID 1的火车票，张三，13800138000"
        )
        assert extract_state(result) in ["completed", "failed", "input-required"]


class TestAgentHealth:
    """测试Agent健康状态"""

    @pytest.mark.asyncio
    async def test_weather_agent_health(self):
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.get(f"{WEATHER_AGENT_URL}/.well-known/agent.json")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ticket_agent_health(self):
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.get(f"{TICKET_AGENT_URL}/.well-known/agent.json")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_order_agent_health(self):
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.get(f"{ORDER_AGENT_URL}/.well-known/agent.json")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
