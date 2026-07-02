# SmartVoyage 智能旅行助手（A2A 多智能体学习项目）

基于 **python-a2a**（A2A 协议社区实现）+ **MCP** + **LLM Text2SQL** 的多 Agent 协同 demo，
Streamlit / CLI 前端，SQLite（默认）/ MySQL 数据层。

> **诚实声明（请先读）**
>
> - 本项目是**学习/演示项目**，所有天气、火车票、机票、演唱会数据均由
>   `scripts/init_data.py` **随机生成（mock）**，不来自任何真实外部 API。
> - 配置项 `MOCK_DATA=true` 显式声明这一点，各 MCP 服务启动时也会打印数据来源。
> - LLM（Text2SQL / 意图识别）是唯一的真实外部依赖；未配置 `LLM_API_KEY` 时，
>   两个离线 demo 仍可完整验证 A2A + MCP + SQL 安全层 + 数据库全链路。

## 功能与真实度

| 功能 | 实现方式 | 真实度 |
|------|---------|--------|
| 天气查询 | LLM 生成 SQL -> 天气 MCP -> 数据库 | 数据 mock |
| 火车票/机票/演唱会查询 | LLM 生成 SQL -> 票务 MCP -> 数据库 | 数据 mock |
| 在线订票 | 订票 Agent --A2A--> 票务 Agent，再经订单 MCP 落库扣减库存 | 数据 mock，流程真实 |
| 景点推荐 | 纯 LLM 生成 | 依赖 LLM |
| 意图识别/多意图路由 | 编排层 LLM | 依赖 LLM |

## 系统架构

```
用户界面层      Streamlit(src/app.py)  /  CLI(src/main.py)
                    │  意图识别 + 路由（编排式，LLM）
                    ▼  A2A 协议 (python-a2a)
业务 Agent 层   WeatherAgent:5005   TicketAgent:5006   OrderAgent:5007
                    │                    ▲ A2A（Agent 间协作）
                    │                    └──── OrderAgent 查余票
                    ▼  MCP 协议 (streamable-http)
数据服务层      WeatherMCP:8000    TicketMCP:8001     OrderMCP:8002
                    │  SQL 安全层 sql_guard（仅 SELECT + 表白名单 + 强制 LIMIT）
                    ▼
数据存储层      SQLite (默认, data/travel_demo.db)  或  MySQL (travel_rag)
```

## 快速开始

环境要求：[uv](https://docs.astral.sh/uv/)（本项目不使用系统 Python / pip）

```bash
git clone <repo>
cd Travel_Agent2Agent
uv sync                       # 安装依赖（pyproject.toml + uv.lock）
```

### 1. 零依赖离线 Demo（无需 LLM Key / MySQL / 外网）

```bash
# 数据层 + SQL 安全防线 + 订单生命周期
uv run python -m scripts.demo_offline

# A2A + MCP 全链路联调（用固定 SQL 模拟 LLM 输出）
uv run python -m scripts.demo_a2a_e2e
```

Windows 控制台如遇编码报错，先执行 `set PYTHONUTF8=1`（或 PowerShell `$env:PYTHONUTF8=1`）。

### 2. 完整服务（需要 LLM Key）

```bash
cp .env.example .env          # 填入 LLM_API_KEY（OpenAI 兼容接口）
uv run python -m scripts.init_data          # 生成 mock 数据（默认 SQLite）

# 逐个启动（或 bash scripts/start_services.sh）
uv run python -m src.mcp_servers.weather_mcp
uv run python -m src.mcp_servers.ticket_mcp
uv run python -m src.mcp_servers.order_mcp
uv run python -m src.agents.weather_agent
uv run python -m src.agents.ticket_agent
uv run python -m src.agents.order_agent

# 前端二选一
uv run streamlit run src/app.py             # http://localhost:8501
uv run python -m src.main                   # CLI
```

### 3. MySQL 后端（可选）

```bash
mysql -u root -p < sql/init_database.sql
# .env: DB_BACKEND=mysql + DB_* 连接信息
uv run python -m scripts.init_data
```

## 测试

```bash
# 单元测试（离线可跑）：SQL 安全层 + 数据校验器
uv run python -m pytest tests/test_sql_guard.py tests/test_validators.py -v

# 集成测试（需服务已启动 + LLM Key）
RUN_INTEGRATION=1 uv run python -m pytest tests/test_agents.py -v

# 服务健康检查
uv run python -m scripts.health_check
```

## Text2SQL 安全防线

LLM 生成的 SQL 属于**不可信输入**，一律经 `src/mcp_servers/sql_guard.py` 校验后才执行：

1. 仅允许**单条 SELECT**（sqlparse 语法级判定 + 正则双保险）
2. 禁止注释 / 多语句 / UNION / 写操作与危险函数关键字
3. **表名白名单**（每个 MCP 服务只能查自己的表）
4. **强制 LIMIT** 上限（防大结果集拖库）

结构化参数入口（如 `query_train_tickets`）全部使用**参数化查询**，无字符串拼接。
详见 `docs/复习笔记.md`。

## 项目结构

```
├── pyproject.toml / uv.lock  # uv 项目与依赖锁定
├── .env.example              # 环境变量模板
├── docs/                     # 文档（含 复习笔记.md）
├── sql/
│   ├── init_database.sql     # MySQL 建库建表
│   └── init_sqlite.sql       # SQLite 建表（离线 demo）
├── scripts/
│   ├── init_data.py          # mock 数据生成（双后端）
│   ├── demo_offline.py       # 离线端到端 demo
│   ├── demo_a2a_e2e.py       # A2A+MCP 全链路联调（模拟 LLM）
│   ├── health_check.py       # 服务健康检查
│   └── start_services.sh     # 一键启动
├── src/
│   ├── main.py / app.py      # CLI / Streamlit 编排层
│   ├── config/               # 配置 + 日志
│   ├── agents/               # A2A Agent（base/weather/ticket/order）
│   ├── mcp_servers/          # MCP 服务（base/sql_guard/weather/ticket/order）
│   ├── prompts/              # Prompt 模板
│   └── utils/                # 校验、格式化
└── tests/                    # 单测 + 集成测试
```

## 已知限制

- 数据全部 mock，随机生成，不具备真实参考价值
- A2A 服务端为 Flask 开发服务器，仅供本地演示
- 订单扣库存/回滚为两步操作，非事务，并发下可能不一致（demo 范围内可接受）
- 未实现支付、退款、用户体系

## License

MIT
