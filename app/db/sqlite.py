"""SQLite 连接管理与只读查询执行。

对应原项目 src/lib/sqlite.ts，但修复其安全隐患：
    原项目对非 SELECT 语句直接 .run()（INSERT/UPDATE 都能执行！）。
    这里用两道防线保证只读：
    1. sqlglot 解析 AST，只放行 SELECT（在 tools/execute_sql.py）
    2. SQLite URI 只读模式连接（mode=ro）——即使第一道被绕过，写操作也会报错
"""

from __future__ import annotations

import sqlite3
import threading
import time

from app.config import settings


class SQLiteError(Exception):
    """查询执行错误，message 返回给模型用于自我修正。"""


# 每线程一个连接：sqlite3 连接默认不允许跨线程共享，
# 而 FastAPI 会在线程池里跑同步代码（run_in_executor）
_local = threading.local()


def get_readonly_conn() -> sqlite3.Connection:
    """获取当前线程的只读连接（懒创建）。

    mode=ro: 操作系统级只读打开，任何写操作抛 "attempt to write a readonly database"。
    """
    conn = getattr(_local, "conn", None)
    if conn is None:
        db_file = settings.db_file
        if not db_file.exists():
            raise SQLiteError(
                f"数据库不存在: {db_file}\n"
                "请先运行: python scripts/init_database.py && python scripts/seed_database.py"
            )
        conn = sqlite3.connect(
            f"file:{db_file.as_posix()}?mode=ro", uri=True, check_same_thread=False
        )
        _local.conn = conn
    return conn


def run_query(sql: str, row_limit: int | None = None) -> dict:
    """执行只读查询，返回结构化结果。

    返回格式与原项目 ExecuteSQL 工具对齐：
        {ok, columns, rows, row_count, execution_time_ms}
    rows 是 list[dict]，方便模型阅读和前端渲染。
    """
    limit = row_limit or settings.sql_row_limit
    start = time.perf_counter()
    try:
        cur = get_readonly_conn().execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        raw = cur.fetchmany(limit)  # 上限保护，防止巨量结果撑爆内存/上下文
    except sqlite3.Error as e:
        raise SQLiteError(f"SQLite Error: {e}") from e

    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    return {
        "ok": True,
        "columns": columns,
        "rows": [dict(zip(columns, r)) for r in raw],
        "row_count": len(raw),
        "execution_time_ms": elapsed_ms,
    }
