#!/usr/bin/env python3
"""
订票Agent
src/agents/order_agent.py

处理票务预订请求，包括信息验证、余票检查、订单创建
"""

import json
import re
import uuid
from typing import Dict, Any, List

from python_a2a import A2AClient, AgentCard, AgentSkill, Task, TaskState

from langchain_core.prompts import ChatPromptTemplate

from src.agents.base_agent import AgentReply, BaseAgent, MCPClientMixin
from src.config import config, logger


# ==================== 意图解析提示词 ====================
INTENT_PROMPT = ChatPromptTemplate.from_template(
    """
你是一个订票意图解析器，需要从用户输入中提取订票相关信息。

【当前日期】{current_date}

【用户输入】{user_input}

【解析规则】
1. 识别订票类型：
   - 火车票/高铁票 → "train"
   - 机票/飞机票 → "flight"  
   - 演唱会票 → "concert"

2. 提取必要信息：
   - 火车票/机票：出发城市、到达城市、日期、座位类型（可选）
   - 演唱会票：城市、艺人、日期、票类型（可选）

3. 提取联系人信息：姓名、电话、身份证号（可选）

4. 如果用户提供了票务ID，直接使用

【输出格式】
如果信息足够，输出JSON：
{{
    "status": "ready",
    "ticket_type": "train/flight/concert",
    "query_params": {{
        "departure_city": "出发城市",
        "arrival_city": "到达城市",
        "city": "城市（演唱会）",
        "artist": "艺人（演唱会）",
        "date": "YYYY-MM-DD",
        "seat_type": "座位类型"
    }},
    "ticket_id": null,
    "quantity": 1,
    "contact": {{
        "name": "联系人姓名",
        "phone": "联系人电话",
        "id_card": "身份证号"
    }}
}}

如果缺少必要信息，输出：
{{
    "status": "input_required",
    "message": "需要补充的具体信息",
    "missing_fields": ["缺少的字段"]
}}

【示例】
用户：订一张明天北京到上海的高铁票，二等座，张三，13800138000
输出：
{{
    "status": "ready",
    "ticket_type": "train",
    "query_params": {{
        "departure_city": "北京",
        "arrival_city": "上海",
        "date": "2026-01-19",
        "seat_type": "二等座"
    }},
    "ticket_id": null,
    "quantity": 1,
    "contact": {{
        "name": "张三",
        "phone": "13800138000",
        "id_card": ""
    }}
}}
"""
)


# ==================== Agent卡片定义 ====================
agent_card = AgentCard(
    name="OrderBookingAgent",
    description="订票代理，支持火车票、机票、演唱会票的在线预订",
    url=f"http://localhost:{config.agents.order_port}",
    version="2.0.0",
    capabilities={
        "streaming": False,
        "pushNotifications": False
    },
    skills=[
        AgentSkill(
            name="book_train_ticket",
            description="预订火车票/高铁票",
            examples=[
                "订一张明天北京到上海的高铁，二等座，张三，13800138000",
                "买票务ID 123的火车票",
            ]
        ),
        AgentSkill(
            name="book_flight_ticket",
            description="预订机票/航班",
            examples=[
                "订1月20日上海到广州的机票，经济舱，李四，13900139000",
            ]
        ),
        AgentSkill(
            name="book_concert_ticket",
            description="预订演唱会门票",
            examples=[
                "订周杰伦北京演唱会的内场票，王五，13700137000",
            ]
        )
    ]
)


class TicketAgentClient:
    """票务 Agent 的 A2A 客户端（Agent 间通信走 A2A 协议）"""

    def __init__(self, agent_url: str):
        self.agent_url = agent_url

    @staticmethod
    def _extract_text(task: Task) -> str:
        """从返回的 Task 中提取文本：完成态取 artifacts，其余取 status.message"""
        if task.status.state == TaskState.COMPLETED and task.artifacts:
            parts = task.artifacts[0].get("parts", [])
            if parts and isinstance(parts[0], dict):
                return parts[0].get("text", "")
        message = task.status.message or {}
        content = message.get("content", {})
        if isinstance(content, dict):
            return content.get("text", "")
        return str(content)

    async def query_tickets(self, query_text: str) -> Dict[str, Any]:
        """调用票务Agent查询余票"""
        try:
            client = A2AClient(self.agent_url, timeout=30)
            task = Task(
                id=f"task-{uuid.uuid4()}",
                message={
                    "role": "user",
                    "content": {"type": "text", "text": query_text},
                },
            )
            result = await client.send_task_async(task)
            logger.info(f"票务Agent响应状态: {result.status.state}")

            state = result.status.state
            return {
                "status": "success" if state == TaskState.COMPLETED else str(state.value),
                "content": self._extract_text(result),
            }

        except Exception as e:
            logger.error(f"调用票务Agent失败: {e}")
            return {"status": "error", "message": str(e)}


class OrderBookingAgent(BaseAgent, MCPClientMixin):
    """订票Agent"""

    def __init__(self):
        super().__init__(agent_card=agent_card)
        self.intent_prompt = INTENT_PROMPT
        self.ticket_client = TicketAgentClient(config.agents.ticket_url)
        self.order_mcp_url = config.mcp.order_url
        logger.info("OrderBookingAgent 初始化完成")

    def get_welcome_message(self) -> str:
        return "请输入您的订票需求，例如：订一张明天北京到上海的高铁票，二等座，张三，13800138000"

    def parse_intent(self, user_input: str) -> Dict[str, Any]:
        """解析用户订票意图"""
        try:
            chain = self.intent_prompt | self.llm

            output = chain.invoke({
                "current_date": self.current_date,
                "user_input": user_input
            }).content.strip()

            logger.info(f"意图解析输出: {output}")

            # 清理markdown代码块
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0]
            elif "```" in output:
                output = output.split("```")[1].split("```")[0]

            return json.loads(output.strip())

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return {
                "status": "input_required",
                "message": "无法理解您的订票需求，请重新描述。"
            }
        except Exception as e:
            logger.error(f"意图解析失败: {e}")
            return {
                "status": "input_required",
                "message": f"处理失败: {str(e)}"
            }

    def build_query_text(self, intent: Dict[str, Any]) -> str:
        """根据意图构建票务查询文本"""
        ticket_type = intent.get("ticket_type", "")
        params = intent.get("query_params", {})

        if ticket_type == "train":
            parts = ["查询火车票"]
            if params.get("date"):
                parts.append(params["date"])
            if params.get("departure_city"):
                parts.append(params["departure_city"])
            if params.get("arrival_city"):
                parts.append(f"到{params['arrival_city']}")
            if params.get("seat_type"):
                parts.append(params["seat_type"])
            return ' '.join(parts)

        elif ticket_type == "flight":
            parts = ["查询机票"]
            if params.get("date"):
                parts.append(params["date"])
            if params.get("departure_city"):
                parts.append(params["departure_city"])
            if params.get("arrival_city"):
                parts.append(f"到{params['arrival_city']}")
            if params.get("cabin_type"):
                parts.append(params["cabin_type"])
            return ' '.join(parts)

        elif ticket_type == "concert":
            parts = ["查询演唱会"]
            if params.get("artist"):
                parts.append(params["artist"])
            if params.get("city"):
                parts.append(params["city"])
            return ' '.join(parts)

        return "查询票务"

    def extract_ticket_ids(self, content: str) -> List[int]:
        """从票务Agent响应中提取票务ID列表"""
        pattern = r'票务ID[：:]\s*(\d+)'
        matches = re.findall(pattern, content)
        return [int(tid) for tid in matches]

    def format_booking_result(self, result: Dict[str, Any]) -> str:
        """格式化订票结果"""
        if result.get("status") == "success":
            data = result.get("data", {})
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except:
                    return f"✅ 订票成功！\n{data}"

            lines = ["✅ 订票成功！\n"]
            lines.append(f"📋 订单号: {data.get('order_no', 'N/A')}")
            lines.append(f"🎫 数量: {data.get('quantity', 1)}张")
            lines.append(f"💰 总价: ¥{data.get('total_price', 'N/A')}")
            lines.append(f"👤 联系人: {data.get('contact_name', 'N/A')}")
            lines.append(f"📱 电话: {data.get('contact_phone', 'N/A')}")
            lines.append(f"\n⏰ 请在30分钟内完成支付")
            return '\n'.join(lines)
        else:
            return f"❌ 订票失败: {result.get('message', '未知错误')}"

    async def _place_order(self, intent: Dict[str, Any], ticket_id: int) -> AgentReply:
        """调用订单MCP下单"""
        contact = intent.get("contact", {})
        order_data = {
            "ticket_type": intent.get("ticket_type", "train"),
            "ticket_id": ticket_id,
            "quantity": intent.get("quantity", 1),
            "contact_name": contact.get("name", ""),
            "contact_phone": contact.get("phone", ""),
            "contact_id_card": contact.get("id_card", "")
        }

        mcp_result = await self.call_mcp_tool(
            self.order_mcp_url,
            "create_order",
            order_data
        )

        # MCP 返回的 data 是订单服务的 JSON 字符串
        order_result = mcp_result
        if mcp_result.get("status") == "success":
            try:
                order_result = json.loads(mcp_result.get("data", "{}"))
            except (json.JSONDecodeError, TypeError):
                order_result = mcp_result

        formatted = self.format_booking_result(order_result)

        if order_result.get("status") == "success":
            return self.create_success_response(formatted)
        return self.create_error_response(formatted)

    async def process(self, user_input: str) -> AgentReply:
        """处理订票请求"""
        logger.info(f"收到订票请求: {user_input}")

        # 1. 解析意图
        intent = self.parse_intent(user_input)
        logger.info(f"解析意图: {intent}")

        # 2. 检查是否需要补充信息
        if intent.get("status") == "input_required":
            return self.create_input_required_response(
                intent.get("message", "请提供更多订票信息")
            )

        # 3. 检查联系人信息
        contact = intent.get("contact", {})
        if not contact.get("name") or not contact.get("phone"):
            return self.create_input_required_response(
                "请提供联系人姓名和手机号码，例如：张三，13800138000"
            )

        # 4. 如果有票务ID，直接下单
        ticket_id = intent.get("ticket_id")
        if ticket_id:
            logger.info(f"使用指定票务ID下单: {ticket_id}")
            return await self._place_order(intent, ticket_id)

        # 5. 调用票务Agent查询余票（A2A 协作）
        query_text = self.build_query_text(intent)
        logger.info(f"查询余票: {query_text}")

        ticket_result = await self.ticket_client.query_tickets(query_text)
        logger.info(f"余票查询结果: {ticket_result}")

        if ticket_result.get("status") == "error":
            return self.create_error_response(
                f"查询余票失败: {ticket_result.get('message')}"
            )

        # 6. 检查余票
        content = ticket_result.get("content", "")

        if "未找到" in content or "没有" in content:
            return self.create_input_required_response(
                f"😔 {content}\n\n请调整您的出行计划：\n- 尝试其他日期\n- 尝试其他座位类型\n- 尝试其他车次/航班"
            )

        # 7. 提取票务ID
        ticket_ids = self.extract_ticket_ids(content)

        if not ticket_ids:
            return self.create_input_required_response(
                f"查询到以下票务信息：\n\n{content}\n\n请提供您要预订的票务ID，例如：订票务ID 123"
            )

        # 8. 唯一选项自动下单，多个选项让用户指定
        if len(ticket_ids) == 1:
            return await self._place_order(intent, ticket_ids[0])

        return self.create_input_required_response(
            f"查询到多个票务选项：\n\n{content}\n\n请指定您要预订的票务ID，例如：订票务ID {ticket_ids[0]}"
        )


# ==================== 主函数 ====================
def main():
    """启动订票服务器"""
    from python_a2a import run_server

    print("=" * 60)
    print("🎫 订票代理 A2A 服务器")
    print("=" * 60)
    print(f"服务地址:     http://localhost:{config.agents.order_port}")
    print(f"票务Agent:    {config.agents.ticket_url}")
    print(f"订票MCP:      {config.mcp.order_url}")
    print("=" * 60)
    print("\n订票示例：")
    print("  🚄 订一张明天北京到上海的高铁，二等座，张三，13800138000")
    print("  ✈️ 买1月20日上海到广州的机票，经济舱，李四，13900139000")
    print("  🎤 订周杰伦北京演唱会内场票，王五，13700137000")
    print("=" * 60)

    server = OrderBookingAgent()

    try:
        run_server(server, host="0.0.0.0", port=config.agents.order_port)
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")
        raise


if __name__ == "__main__":
    main()
