#!/usr/bin/env python3
"""
SmartVoyage 票务查询Agent
src/agents/ticket_agent.py

处理火车票、机票、演唱会票的自然语言查询
"""

import json
from typing import Dict, Any

from python_a2a import AgentCard, AgentSkill, run_server
from langchain_core.prompts import ChatPromptTemplate

from src.config import config, logger
from src.agents.base_agent import AgentReply, BaseAgent, MCPClientMixin


# 数据表Schema定义
TABLE_SCHEMA = """
-- 火车票表
CREATE TABLE train_tickets (
    id INT PRIMARY KEY,
    departure_city VARCHAR(50) COMMENT '出发城市',
    arrival_city VARCHAR(50) COMMENT '到达城市',
    departure_time DATETIME COMMENT '出发时间',
    arrival_time DATETIME COMMENT '到达时间',
    train_number VARCHAR(20) COMMENT '车次号',
    seat_type VARCHAR(20) COMMENT '座位类型（二等座/一等座/商务座）',
    remaining_seats INT COMMENT '剩余座位数',
    price DECIMAL(10,2) COMMENT '票价'
);

-- 机票表
CREATE TABLE flight_tickets (
    id INT PRIMARY KEY,
    departure_city VARCHAR(50) COMMENT '出发城市',
    arrival_city VARCHAR(50) COMMENT '到达城市',
    departure_time DATETIME COMMENT '出发时间',
    arrival_time DATETIME COMMENT '到达时间',
    flight_number VARCHAR(20) COMMENT '航班号',
    cabin_type VARCHAR(20) COMMENT '舱位类型（经济舱/商务舱/头等舱）',
    remaining_seats INT COMMENT '剩余座位数',
    price DECIMAL(10,2) COMMENT '票价'
);

-- 演唱会票表
CREATE TABLE concert_tickets (
    id INT PRIMARY KEY,
    artist VARCHAR(100) COMMENT '艺人名称',
    city VARCHAR(50) COMMENT '举办城市',
    venue VARCHAR(100) COMMENT '场馆',
    start_time DATETIME COMMENT '开始时间',
    end_time DATETIME COMMENT '结束时间',
    ticket_type VARCHAR(20) COMMENT '票类型（看台票/内场票/VIP票）',
    remaining_seats INT COMMENT '剩余座位数',
    price DECIMAL(10,2) COMMENT '票价'
);
"""

# SQL生成Prompt
SQL_PROMPT = ChatPromptTemplate.from_template("""
你是一个专业的票务SQL生成器。根据用户的自然语言查询，生成对应的SQL语句。

【数据表结构】
{table_schema}

【当前日期】
{current_date}

【用户查询】
{user_query}

【生成规则】
1. 识别查询类型：
   - 火车票/高铁票 → train_tickets 表
   - 机票/飞机票 → flight_tickets 表
   - 演唱会票 → concert_tickets 表

2. 必要信息检查：
   - 火车票/机票：需要出发城市、到达城市、日期
   - 演唱会票：需要城市或艺人
   - 如果缺少必要信息，返回追问JSON

3. 日期处理：
   - "明天" → 当前日期+1天
   - "后天" → 当前日期+2天
   - "下周" → 未来7天范围

4. 只查询有余票的记录：remaining_seats > 0

【输出格式】
如果信息完整，输出两行：
第一行：{{"type": "train/flight/concert"}}
第二行：SELECT语句

如果信息不足，输出：
{{"status": "input_required", "message": "需要补充的信息"}}

【示例】
用户：明天北京到上海的高铁票
输出：
{{"type": "train"}}
SELECT id, departure_city, arrival_city, departure_time, arrival_time, train_number, seat_type, price, remaining_seats FROM train_tickets WHERE departure_city = '北京' AND arrival_city = '上海' AND DATE(departure_time) = '2026-01-19' AND remaining_seats > 0 ORDER BY departure_time LIMIT 10
""")


# Agent卡片定义
TICKET_AGENT_CARD = AgentCard(
    name="TicketQueryAgent",
    description="票务查询代理，支持火车票、机票、演唱会票的自然语言查询",
    url=f"http://localhost:{config.agents.ticket_port}",
    version="2.0.0",
    capabilities={
        "streaming": False,
        "pushNotifications": False
    },
    skills=[
        AgentSkill(
            name="query_train_ticket",
            description="查询火车票/高铁票信息",
            examples=["查询明天北京到上海的高铁", "1月20日广州到深圳的火车票"]
        ),
        AgentSkill(
            name="query_flight_ticket",
            description="查询机票/航班信息",
            examples=["查询上海到北京的机票", "明天深圳飞广州的经济舱"]
        ),
        AgentSkill(
            name="query_concert_ticket",
            description="查询演唱会门票信息",
            examples=["周杰伦北京演唱会", "五月天上海站门票"]
        )
    ]
)


class TicketQueryAgent(BaseAgent, MCPClientMixin):
    """票务查询Agent"""
    
    def __init__(self):
        super().__init__(agent_card=TICKET_AGENT_CARD)
        self.sql_prompt = SQL_PROMPT
        self.mcp_url = config.mcp.ticket_url
    
    def get_welcome_message(self) -> str:
        return "请输入您的票务查询需求，例如：查询明天北京到上海的高铁票"
    
    def generate_sql(self, user_query: str) -> Dict[str, Any]:
        """
        使用LLM生成SQL
        
        Args:
            user_query: 用户查询文本
            
        Returns:
            包含type和sql的字典，或追问信息
        """
        try:
            chain = self.sql_prompt | self.llm
            
            output = chain.invoke({
                "table_schema": TABLE_SCHEMA,
                "current_date": self.current_date,
                "user_query": user_query
            }).content.strip()
            
            logger.info(f"LLM输出: {output}")
            
            # 清理markdown代码块
            if "```" in output:
                lines = []
                in_code = False
                for line in output.split('\n'):
                    if line.strip().startswith('```'):
                        in_code = not in_code
                        continue
                    if not in_code or line.strip():
                        lines.append(line)
                output = '\n'.join(lines).strip()
            
            # 解析输出
            lines = output.strip().split('\n')
            first_line = lines[0].strip()
            
            # 检查是否是追问
            if first_line.startswith('{"status"'):
                return json.loads(first_line)
            
            # 解析类型和SQL
            if first_line.startswith('{"type"'):
                query_type = json.loads(first_line).get("type")
                sql = ' '.join(line.strip() for line in lines[1:] if line.strip())
                return {"status": "sql", "type": query_type, "sql": sql}
            
            # 尝试直接作为SQL
            if "SELECT" in output.upper():
                return {"status": "sql", "type": "unknown", "sql": output}
            
            return {"status": "input_required", "message": "无法理解您的查询，请提供更多信息。"}
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return {"status": "input_required", "message": "解析失败，请重新描述您的需求。"}
        except Exception as e:
            logger.error(f"SQL生成失败: {e}")
            return {"status": "input_required", "message": f"处理失败: {str(e)}"}
    
    def format_results(self, query_type: str, data: str) -> str:
        """
        格式化查询结果
        
        Args:
            query_type: 查询类型
            data: JSON格式的查询结果
            
        Returns:
            格式化后的文本
        """
        try:
            records = json.loads(data) if isinstance(data, str) else data
            
            if not records:
                return "😔 未找到符合条件的票务信息，请尝试调整查询条件。"
            
            if isinstance(records, dict):
                if records.get("status") == "no_data":
                    return "😔 " + records.get("message", "未找到数据")
                if records.get("status") == "error":
                    return f"查询失败: {records.get('message', '未知错误')}"
                records = records.get("data", [records])
            
            if not records:
                return "😔 未找到符合条件的票务信息。"
            
            lines = []
            
            if query_type == "train":
                lines.append(f"🚄 找到 {len(records)} 条火车票信息：\n")
                for i, t in enumerate(records, 1):
                    lines.append(f"【{i}】{t.get('train_number', '')} {t.get('seat_type', '')}")
                    lines.append(f"    {t.get('departure_city', '')} → {t.get('arrival_city', '')}")
                    lines.append(f"    出发: {t.get('departure_time', '')}")
                    lines.append(f"    到达: {t.get('arrival_time', '')}")
                    lines.append(f"    💰 ¥{t.get('price', '')} | 余票: {t.get('remaining_seats', '')}张")
                    lines.append(f"    🎫 票务ID: {t.get('id', '')}")
                    lines.append("")
                    
            elif query_type == "flight":
                lines.append(f"✈️ 找到 {len(records)} 条机票信息：\n")
                for i, t in enumerate(records, 1):
                    lines.append(f"【{i}】{t.get('flight_number', '')} {t.get('cabin_type', '')}")
                    lines.append(f"    {t.get('departure_city', '')} → {t.get('arrival_city', '')}")
                    lines.append(f"    出发: {t.get('departure_time', '')}")
                    lines.append(f"    到达: {t.get('arrival_time', '')}")
                    lines.append(f"    💰 ¥{t.get('price', '')} | 余票: {t.get('remaining_seats', '')}张")
                    lines.append(f"    🎫 票务ID: {t.get('id', '')}")
                    lines.append("")
                    
            elif query_type == "concert":
                lines.append(f"🎤 找到 {len(records)} 条演唱会信息：\n")
                for i, t in enumerate(records, 1):
                    lines.append(f"【{i}】{t.get('artist', '')} - {t.get('ticket_type', '')}")
                    lines.append(f"    📍 {t.get('city', '')} · {t.get('venue', '')}")
                    lines.append(f"    🕐 {t.get('start_time', '')}")
                    lines.append(f"    💰 ¥{t.get('price', '')} | 余票: {t.get('remaining_seats', '')}张")
                    lines.append(f"    🎫 票务ID: {t.get('id', '')}")
                    lines.append("")
            else:
                return f"查询结果: {data}"
            
            lines.append("💡 如需订票，请提供票务ID和联系人信息")
            return '\n'.join(lines)
            
        except json.JSONDecodeError:
            return f"查询结果: {data}"
        except Exception as e:
            logger.error(f"格式化结果失败: {e}")
            return f"查询结果: {data}"
    
    async def process(self, user_input: str) -> AgentReply:
        """处理票务查询"""
        logger.info(f"收到票务查询: {user_input}")

        # 生成SQL
        sql_result = self.generate_sql(user_input)
        logger.info(f"SQL生成结果: {sql_result}")

        # 处理追问
        if sql_result.get("status") == "input_required":
            return self.create_input_required_response(
                sql_result.get("message", "请提供更多信息")
            )

        # 执行查询
        if sql_result.get("status") == "sql":
            query_type = sql_result.get("type", "unknown")
            sql = sql_result.get("sql", "")

            # 调用MCP
            mcp_result = await self.call_mcp_tool(
                self.mcp_url,
                "query_tickets",
                {"sql": sql}
            )

            if mcp_result.get("status") == "error":
                return self.create_error_response(f"查询失败: {mcp_result.get('message')}")

            # 格式化结果
            formatted = self.format_results(query_type, mcp_result.get("data", ""))
            return self.create_success_response(formatted)

        return self.create_error_response("无法处理您的请求，请重试。")


def main():
    """启动票务查询Agent"""
    print("=" * 60)
    print("🎫 票务查询 Agent 服务器")
    print("=" * 60)
    print(f"服务地址: {TICKET_AGENT_CARD.url}")
    print(f"MCP地址:  {config.mcp.ticket_url}")
    print("=" * 60)
    print("\n支持的查询：")
    print("  🚄 火车票: 明天北京到上海的高铁")
    print("  ✈️ 机票:   上海飞广州经济舱")
    print("  🎤 演唱会: 周杰伦北京演唱会")
    print("=" * 60)
    
    agent = TicketQueryAgent()
    
    try:
        run_server(agent, host=config.agents.ticket_host, port=config.agents.ticket_port)
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")
        raise


if __name__ == "__main__":
    main()
