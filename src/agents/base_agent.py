#!/usr/bin/env python3
"""
Agent 基类
src/agents/base_agent.py

统一响应构造、输入提取、LLM 初始化、MCP 调用
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from python_a2a import A2AServer, AgentCard, Task, TaskState, TaskStatus
import pytz

from src.config import config, logger


@dataclass
class AgentReply:
    """Agent 处理结果：状态 + 文本"""
    state: TaskState
    text: str


class BaseAgent(A2AServer, ABC):
    """
    A2A Agent 抽象基类

    python_a2a 的服务端以同步方式调用 handle_task(task) 并要求返回 Task，
    这里将其固化为模板方法：提取输入 -> 调用子类异步 process -> 回填 Task
    """

    def __init__(self, agent_card: AgentCard):
        super().__init__(agent_card=agent_card)
        self.agent_card = agent_card
        self.timezone = pytz.timezone(config.timezone)
        self._llm = None
        logger.info(f"{self.agent_card.name} 初始化完成")

    @property
    def llm(self):
        """惰性初始化 LLM，未配置密钥时给出明确错误"""
        if self._llm is None:
            if not config.llm.api_key:
                raise RuntimeError("未配置 LLM_API_KEY，无法调用大模型")
            from langchain_openai import ChatOpenAI
            self._llm = ChatOpenAI(
                model=config.llm.model_name,
                base_url=config.llm.base_url,
                api_key=config.llm.api_key,
                temperature=config.llm.temperature,
                max_tokens=config.llm.max_tokens,
            )
        return self._llm

    @llm.setter
    def llm(self, value):
        # 允许注入替身模型（离线 demo / 测试）
        self._llm = value

    @property
    def current_date(self) -> str:
        return datetime.now(self.timezone).strftime('%Y-%m-%d')

    @property
    def current_datetime(self) -> str:
        return datetime.now(self.timezone).strftime('%Y-%m-%d %H:%M:%S')

    # ---------- 响应构造 ----------

    def create_success_response(self, content: str) -> AgentReply:
        return AgentReply(TaskState.COMPLETED, content)

    def create_error_response(self, content: str) -> AgentReply:
        return AgentReply(TaskState.FAILED, content)

    def create_input_required_response(self, content: str) -> AgentReply:
        return AgentReply(TaskState.INPUT_REQUIRED, content)

    # ---------- 任务处理 ----------

    def extract_user_input(self, task: Task) -> str:
        """从 A2A 任务中提取用户文本（兼容 dict / list / str 三种 content 形态）"""
        message = getattr(task, 'message', None)
        if not message:
            return ""
        if isinstance(message, str):
            return message
        content = message.get('content') if isinstance(message, dict) else getattr(message, 'content', None)
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return content.get('text', "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and 'text' in item:
                    return item['text']
                if hasattr(item, 'text'):
                    return item.text
        return ""

    def handle_task(self, task: Task) -> Task:
        """python_a2a 服务端入口（同步），封装异步业务处理"""
        try:
            user_input = self.extract_user_input(task)
            if not user_input:
                reply = self.create_input_required_response(self.get_welcome_message())
            else:
                reply = asyncio.run(self.process(user_input))
        except Exception as e:
            logger.error(f"{self.agent_card.name} 处理任务失败: {e}", exc_info=True)
            reply = self.create_error_response(f"处理请求时发生错误: {e}")

        task.status = TaskStatus(
            state=reply.state,
            message={
                "role": "agent",
                "content": {"type": "text", "text": reply.text},
            },
        )
        if reply.state == TaskState.COMPLETED:
            task.artifacts = [{"parts": [{"type": "text", "text": reply.text}]}]
        return task

    @abstractmethod
    async def process(self, user_input: str) -> AgentReply:
        """子类实现：处理用户输入，返回 AgentReply"""

    @abstractmethod
    def get_welcome_message(self) -> str:
        """子类实现：空输入时的欢迎/引导语"""


class MCPClientMixin:
    """MCP 客户端混入：通过 streamable-http 调用 MCP 工具"""

    async def call_mcp_tool(
        self,
        mcp_url: str,
        tool_name: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        try:
            async with streamablehttp_client(mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    logger.debug(f"调用MCP工具: {tool_name}, 参数: {params}")
                    result = await session.call_tool(tool_name, params)
                    if hasattr(result, 'content') and result.content:
                        return {"status": "success", "data": result.content[0].text}
                    return {"status": "success", "data": str(result)}
        except Exception as e:
            logger.error(f"MCP调用失败: {e}")
            return {"status": "error", "message": str(e)}
