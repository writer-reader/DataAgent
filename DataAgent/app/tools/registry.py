"""工具注册表 —— 统一的 schema 汇总与分发执行。

Agent 循环只跟本模块打交道：
    TOOL_SCHEMAS  -> 传给 OpenAI API 的 tools 参数
    execute_tool  -> 按名字分发到具体实现，永不抛异常（错误以 dict 返回给模型）
"""

from __future__ import annotations

import json
from typing import Any, Callable

from app.retrieval import ToolError
from app.tools.execute_sql import EXECUTE_SQL_TOOL_SCHEMA, execute_sql
from app.tools.explore import EXPLORE_TOOL_SCHEMAS, list_files, read_file, search
from app.tools.finalize import FINALIZE_TOOL_SCHEMA, finalize_report

# 完整工具清单，顺序无关紧要
TOOL_SCHEMAS: list[dict] = [
    *EXPLORE_TOOL_SCHEMAS,
    EXECUTE_SQL_TOOL_SCHEMA,
    FINALIZE_TOOL_SCHEMA,
]

# 名字 -> 可调用对象。新增工具时在这里注册即可
_HANDLERS: dict[str, Callable[..., Any]] = {
    "list_files": list_files,
    "read_file": read_file,
    "search": search,
    "ExecuteSQL": execute_sql,
    "FinalizeReport": finalize_report,
}


def execute_tool(name: str, arguments_json: str) -> Any:
    """执行一个工具调用。

    arguments_json 是模型产出的 JSON 字符串（OpenAI 流式拼装后的 arguments）。
    所有错误都转成可读的返回值——模型看到错误信息才能自我修正；
    抛异常只会中断整个 Agent 循环。
    """
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "error": f"未知工具: {name}"}

    try:
        kwargs = json.loads(arguments_json) if arguments_json.strip() else {}
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"工具参数不是合法 JSON: {e}"}
    if not isinstance(kwargs, dict):
        return {"ok": False, "error": "工具参数必须是 JSON 对象"}

    try:
        return handler(**kwargs)
    except ToolError as e:
        # 预期内的工具错误（文件不存在、路径越界等）
        return {"ok": False, "error": str(e)}
    except TypeError as e:
        # 参数名/个数不匹配（模型幻觉出不存在的参数）
        return {"ok": False, "error": f"工具参数错误: {e}"}
    except Exception as e:  # 兜底：任何意外都不中断循环
        return {"ok": False, "error": f"工具执行异常: {type(e).__name__}: {e}"}


def result_to_str(result: Any) -> str:
    """把工具结果序列化为字符串（塞进 role=tool 消息）。

    字符串结果（read_file/search 等）直接用；dict 用 JSON。
    ensure_ascii=False 保证中文可读，模型处理原文比 \\uXXXX 转义更稳。
    """
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)
