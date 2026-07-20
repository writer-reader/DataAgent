# DataAgent — Python 版 AI 数据分析师

一个通过 **探索语义层 → 构建 SQL → 执行 → 生成叙述性报告** 来回答自然语言数据问题的 AI Agent。

核心设计（继承原作）：**数据库 schema 不进 prompt**。Agent 通过探索工具动态阅读语义层
YAML 文件（像人类分析师翻数据字典一样），再据此写 SQL——换 schema 无需改任何代码。

## 快速开始

```bash
# 1. 安装依赖（建议虚拟环境）
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. 配置（填入你的 OpenAI 兼容 API key / base_url / 模型名）
cp .env.example .env

# 3. 初始化数据库（50 公司 / 500 员工 / 200 账户示例数据）
python scripts/init_database.py
python scripts/seed_database.py

# 4a. CLI 方式（最快验证）
python -m app.cli "各行业分别有多少家公司？"
python -m app.cli          # 交互模式

# 4b. Web 方式
uvicorn app.main:app --reload --port 8000
# 打开 http://localhost:8000
```

## 项目结构

```
app/
├── config.py            # pydantic-settings 配置（.env 加载）
├── main.py              # FastAPI: /api/chat SSE 路由 + 静态前端
├── cli.py               # 命令行入口（rich 渲染）
├── agent/
│   ├── loop.py          # ★ Agent 核心循环（OpenAI SDK 流式 + 工具往返）
│   ├── prompts.py       # System Prompt
│   └── events.py        # SSE 事件协议（text/tool_call/tool_result/report/...）
├── tools/
│   ├── registry.py      # 工具注册表（schema 汇总 + 分发执行）
│   ├── explore.py       # list_files/read_file/search（替代原作的沙箱 bash）
│   ├── execute_sql.py   # SQL 执行（sqlglot 只放行 SELECT）
│   └── finalize.py      # FinalizeReport（结构化收尾 + 循环终止信号）
├── retrieval/
│   └── base.py          # ★ RAG 预留接口（SemanticRetriever 协议）
└── db/
    └── sqlite.py        # 只读连接（mode=ro）+ 查询执行
semantic/                # 语义层（YAML 格式与原项目 100% 兼容）
scripts/                 # init/seed 数据库脚本
static/index.html        # 单文件聊天前端（SSE 流式渲染）
tests/                   # pytest 单测
```

## 工作原理

```
用户提问 → Agent 循环（最多 100 步）:
  ① read_file("catalog.yml")          浏览实体目录
  ② read_file("entities/Xxx.yml")     查表名/字段/join
  ③ ExecuteSQL(SELECT ...)            出错则改 SQL 重试（最多 2 次）
  ④ FinalizeReport(sql, csv, 叙述)    → 循环终止
→ 全程 SSE 流式推送: 思考文本 / 工具卡片 / 最终报表
```

## 安全设计（比原作更严格）

- SQL 经 **sqlglot AST 校验**，只放行单条 SELECT（原作可执行 INSERT）
- SQLite 以 **`mode=ro` 只读模式** 连接，双保险
- 探索工具锁定在 `semantic/` 目录，**防路径穿越**（`../` 越界直接拒绝）

## RAG 预留（语义层膨胀后的扩展点）

初版不含 RAG（保持原作"Agent 自己翻文档"的风味）。当实体增长到数百个时：

1. 实现 `app/retrieval/base.py` 中注释的 `VectorRetriever`
   （按实体粒度 embedding，用 name+description+example_questions 做向量文本）
2. `.env` 改 `RETRIEVER=vector`
3. 工具层与 Agent 循环**零改动**——RAG 只预筛选"哪些文件可见"，
   `read_file` 永远返回完整 YAML，保证 SQL 构建信息不残缺

## 换成你自己的数据

1. 把你的表建到 SQLite（或改 `app/db/sqlite.py` 接其他库）
2. 在 `semantic/entities/` 下为每张表写一个 YAML（参考现有文件格式）
3. 更新 `semantic/catalog.yml` 索引
4. 完成——Agent 会自动发现新 schema，无需改代码

## 测试

```bash
pytest tests/ -v
```
