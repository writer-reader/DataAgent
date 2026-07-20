"""ExecuteSQL 工具 —— SQL 校验 + 只读执行。

对应原项目 src/lib/tools/execute-sqlite.ts，增强安全性：
    1. sqlglot 解析 AST，只放行单条 SELECT（原项目无此校验，INSERT 也能跑）
    2. 底层连接本身是 mode=ro 只读（见 app/db/sqlite.py）

错误不抛异常而是返回 {ok: False, error: ...}——
模型看到错误信息后会自行修正 SQL 重试（system prompt 中有相应指引）。
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.db import SQLiteError, run_query


def _validate_select(sql: str) -> str | None:
    """校验 SQL 是否为单条只读 SELECT。合法返回 None，否则返回错误说明。"""
    try:
        statements = sqlglot.parse(sql, dialect="sqlite")
    except sqlglot.errors.ParseError as e:
        return f"SQL 语法解析失败: {e}"

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return f"只允许单条语句，收到 {len(statements)} 条"

    stmt = statements[0]
    # SELECT ... 或 WITH ... AS (...) SELECT ... 都是合法的只读查询
    # 其它（Insert/Update/Delete/Create/Drop/Pragma...）一律拒绝
    is_select = isinstance(stmt, exp.Select) or (
        isinstance(stmt, exp.With) and isinstance(stmt.this, exp.Select)
    )
    if not is_select:
        return f"仅允许 SELECT 查询，收到: {type(stmt).__name__}"
    return None


def execute_sql(sql: str) -> dict:
    """执行只读 SQL，返回 {ok, columns, rows, row_count, execution_time_ms} 或 {ok: False, error}。"""
    if error := _validate_select(sql):
        return {"ok": False, "error": error, "rows": [], "columns": []}
    try:
        return run_query(sql)
    except SQLiteError as e:
        # 错误信息原样给模型，供其分析并修正 SQL（如列名拼错、表不存在）
        return {"ok": False, "error": str(e), "rows": [], "columns": []}


EXECUTE_SQL_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ExecuteSQL",
        "description": (
            "Execute a read-only SQL SELECT query against the SQLite database. "
            "Returns rows and columns. On error, analyze the message, fix the SQL "
            "and try a DIFFERENT query — never retry identical SQL."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A single SQLite SELECT statement (LIMIT 1001 recommended)",
                }
            },
            "required": ["sql"],
        },
    },
}
