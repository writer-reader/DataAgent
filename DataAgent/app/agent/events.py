"""流式事件模型 —— Agent 循环与前端之间的协议。

Agent 循环 yield 这些事件对象；FastAPI 层把它们序列化为 SSE；
前端按 type 分发渲染。对应原项目 UI Message Stream 的简化版。

事件类型一览:
    text        文本增量（模型的思考/说明文字）
    tool_call   模型发起工具调用（前端显示折叠卡片）
    tool_result 工具执行结果（填充卡片）
    report      最终报告（FinalizeReport 的产出，前端渲染表格）
    done        流结束
    error       出错
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class AgentEvent(BaseModel):
    """所有事件的基类。type 字段用于前端分发。"""

    type: str


class TextDelta(AgentEvent):
    type: Literal["text"] = "text"
    delta: str


class ToolCallEvent(AgentEvent):
    type: Literal["tool_call"] = "tool_call"
    name: str
    arguments: dict[str, Any]  # 已解析的参数（原始 JSON 解析失败时为 {"_raw": ...}）


class ToolResultEvent(AgentEvent):
    type: Literal["tool_result"] = "tool_result"
    name: str
    output: Any                 # dict 或 str，前端按需展示
    truncated: bool = False     # 输出过长被截断时置 True（仅影响展示，不影响模型）


class ReportEvent(AgentEvent):
    type: Literal["report"] = "report"
    sql: str
    csv_results: str
    narrative: str


class DoneEvent(AgentEvent):
    type: Literal["done"] = "done"


class ErrorEvent(AgentEvent):
    type: Literal["error"] = "error"
    message: str
