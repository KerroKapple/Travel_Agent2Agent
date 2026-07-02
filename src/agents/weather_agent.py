#!/usr/bin/env python3
"""
天气查询 Agent
src/agents/weather_agent.py

自然语言 -> LLM 生成 SQL -> 天气 MCP 查询 -> 格式化输出
"""

import json
from typing import Any, Dict

from python_a2a import AgentCard, AgentSkill
from langchain_core.prompts import ChatPromptTemplate

from src.agents.base_agent import AgentReply, BaseAgent, MCPClientMixin
from src.config import config, logger


# ==================== SQL生成提示词 ====================
SQL_PROMPT = ChatPromptTemplate.from_template(
    """
你是一个专业的天气查询SQL生成器。根据用户的自然语言查询，生成对应的SQL语句。

【数据表结构】
CREATE TABLE weather_data (
    id INT PRIMARY KEY,
    city VARCHAR(50) NOT NULL COMMENT '城市名称',
    fx_date DATE NOT NULL COMMENT '预报日期',
    sunrise TIME COMMENT '日出时间',
    sunset TIME COMMENT '日落时间',
    temp_max INT COMMENT '最高温度',
    temp_min INT COMMENT '最低温度',
    text_day VARCHAR(20) COMMENT '白天天气描述',
    text_night VARCHAR(20) COMMENT '夜间天气描述',
    wind_dir_day VARCHAR(20) COMMENT '白天风向',
    wind_scale_day VARCHAR(10) COMMENT '白天风力等级',
    humidity INT COMMENT '相对湿度',
    precip DECIMAL(5,1) COMMENT '降水量',
    uv_index INT COMMENT '紫外线指数',
    vis INT COMMENT '能见度'
);

【当前日期】
{current_date}

【用户查询】
{user_query}

【生成规则】
1. 支持的城市：北京、上海、广州、深圳
2. 如果用户说"今天"，使用当前日期
3. 如果用户说"明天"，使用当前日期+1天
4. 如果用户说"后天"，使用当前日期+2天
5. 如果用户说"这周"或"未来几天"，查询未来7天
6. 只允许生成单条SELECT语句，禁止任何写操作
7. 如果缺少城市信息，返回追问JSON

【输出格式】
如果信息完整，直接输出SELECT语句（查询字段：city, fx_date, temp_max, temp_min, text_day, text_night, humidity, wind_dir_day, wind_scale_day, precip, uv_index）

如果信息不足，输出：
{{"status": "input_required", "message": "具体需要补充的信息"}}

【示例】
用户：北京明天天气
输出：SELECT city, fx_date, temp_max, temp_min, text_day, text_night, humidity, wind_dir_day, wind_scale_day, precip, uv_index FROM weather_data WHERE city = '北京' AND fx_date = '2026-01-19'

用户：天气
输出：{{"status": "input_required", "message": "请告诉我您想查询哪个城市的天气？目前支持：北京、上海、广州、深圳"}}
"""
)


# ==================== Agent卡片定义 ====================
agent_card = AgentCard(
    name="WeatherQueryAgent",
    description="天气查询代理，提供城市天气预报查询服务（本地mock数据）",
    url=f"http://localhost:{config.agents.weather_port}",
    version="2.0.0",
    capabilities={
        "streaming": False,
        "pushNotifications": False
    },
    skills=[
        AgentSkill(
            name="query_weather",
            description="查询指定城市的天气预报",
            examples=[
                "北京今天天气怎么样",
                "上海明天会下雨吗",
                "广州这周天气预报",
                "深圳后天温度多少"
            ]
        )
    ]
)


class WeatherQueryAgent(BaseAgent, MCPClientMixin):
    """天气查询Agent"""

    def __init__(self):
        super().__init__(agent_card=agent_card)
        self.sql_prompt = SQL_PROMPT
        self.mcp_url = config.mcp.weather_url

    def get_welcome_message(self) -> str:
        return "请输入您的天气查询需求，例如：北京明天天气怎么样"

    def generate_sql(self, user_query: str) -> Dict[str, Any]:
        """LLM 生成 SQL 或追问信息"""
        try:
            chain = self.sql_prompt | self.llm
            output = chain.invoke({
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

            if output.startswith('{"status"'):
                return json.loads(output)

            if "SELECT" in output.upper():
                return {"status": "sql", "sql": output}

            return {"status": "input_required", "message": "无法理解您的查询，请提供城市和日期信息。"}

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return {"status": "input_required", "message": "请重新描述您的天气查询需求。"}
        except Exception as e:
            logger.error(f"SQL生成失败: {e}")
            return {"status": "input_required", "message": f"处理失败: {str(e)}"}

    def format_weather_results(self, data: str) -> str:
        """格式化天气查询结果"""
        try:
            records = json.loads(data) if isinstance(data, str) else data

            if not records:
                return "😔 未找到天气数据，请确认城市名称是否正确（支持：北京、上海、广州、深圳）。"

            if isinstance(records, dict):
                if records.get("status") == "no_data":
                    return "😔 未找到天气数据，请确认城市和日期是否正确。"
                if records.get("status") == "error":
                    return f"查询失败: {records.get('message', '未知错误')}"
                if "data" in records:
                    records = records["data"]
                else:
                    records = [records]

            lines = [f"🌤️ 天气预报查询结果：\n"]

            for w in records:
                city = w.get('city', '未知')
                date = w.get('fx_date', '未知')
                temp_max = w.get('temp_max', '-')
                temp_min = w.get('temp_min', '-')
                text_day = w.get('text_day', '-')
                text_night = w.get('text_night', '-')
                humidity = w.get('humidity', '-')
                wind_dir = w.get('wind_dir_day', '-')
                wind_scale = w.get('wind_scale_day', '-')
                precip = w.get('precip', 0)
                uv_index = w.get('uv_index', '-')

                weather_icon = self._get_weather_icon(text_day)

                lines.append(f"📍 {city} - {date}")
                lines.append(f"   {weather_icon} {text_day} / {text_night}")
                lines.append(f"   🌡️ 温度: {temp_min}°C ~ {temp_max}°C")
                lines.append(f"   💧 湿度: {humidity}%")
                lines.append(f"   🌬️ 风向: {wind_dir} {wind_scale}级")
                if float(precip or 0) > 0:
                    lines.append(f"   🌧️ 降水: {precip}mm")
                lines.append(f"   ☀️ 紫外线指数: {uv_index}")
                lines.append("")

            # 温馨提示
            if records:
                first = records[0]
                temp_max = int(first.get('temp_max', 20) or 20)
                text_day = first.get('text_day', '')

                tips = []
                if temp_max >= 35:
                    tips.append("🔥 高温预警，注意防暑降温")
                elif temp_max <= 5:
                    tips.append("❄️ 天气寒冷，注意保暖")
                if '雨' in text_day:
                    tips.append("🌂 记得带伞")
                if '雪' in text_day:
                    tips.append("⛄ 注意路滑")
                if tips:
                    lines.append("💡 温馨提示: " + "，".join(tips))

            return '\n'.join(lines)

        except json.JSONDecodeError:
            return f"天气数据: {data}"
        except Exception as e:
            logger.error(f"格式化天气结果失败: {e}")
            return f"天气数据: {data}"

    def _get_weather_icon(self, weather_text: str) -> str:
        weather_icons = {
            '晴': '☀️',
            '多云': '⛅',
            '阴': '☁️',
            '小雨': '🌦️',
            '中雨': '🌧️',
            '大雨': '🌧️',
            '暴雨': '⛈️',
            '雷阵雨': '⛈️',
            '小雪': '🌨️',
            '中雪': '❄️',
            '大雪': '❄️',
            '雾': '🌫️',
            '霾': '😷',
        }
        for key, icon in weather_icons.items():
            if key in (weather_text or ''):
                return icon
        return '🌤️'

    async def process(self, user_input: str) -> AgentReply:
        """处理天气查询"""
        logger.info(f"收到天气查询: {user_input}")

        sql_result = self.generate_sql(user_input)
        logger.info(f"SQL生成结果: {sql_result}")

        if sql_result.get("status") == "input_required":
            return self.create_input_required_response(
                sql_result.get("message", "请提供更多信息")
            )

        if sql_result.get("status") == "sql":
            mcp_result = await self.call_mcp_tool(
                self.mcp_url,
                "query_weather",
                {"sql": sql_result.get("sql", "")}
            )

            if mcp_result.get("status") == "error":
                return self.create_error_response(
                    f"查询失败: {mcp_result.get('message')}"
                )

            formatted = self.format_weather_results(mcp_result.get("data", ""))
            return self.create_success_response(formatted)

        return self.create_error_response("无法处理您的请求，请重试。")


# ==================== 主函数 ====================
def main():
    """启动天气查询服务器"""
    from python_a2a import run_server

    print("=" * 60)
    print("🌤️ 天气查询 A2A 服务器")
    print("=" * 60)
    print(f"服务地址: http://localhost:{config.agents.weather_port}")
    print(f"MCP地址:  {config.mcp.weather_url}")
    print("=" * 60)
    print("\n支持的查询：")
    print("  🏙️ 城市: 北京、上海、广州、深圳")
    print("  📅 时间: 今天、明天、后天、未来一周")
    print("=" * 60)

    server = WeatherQueryAgent()

    try:
        run_server(server, host="0.0.0.0", port=config.agents.weather_port)
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        logger.error(f"服务器启动失败: {e}")
        raise


if __name__ == "__main__":
    main()
