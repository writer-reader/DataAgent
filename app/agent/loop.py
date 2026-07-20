"""Agent 核心循环 —— 项目的心脏。

对应原项目 agent.ts 的 streamText({tools, stopWhen}) 循环，用 OpenAI SDK 手写。

一轮循环 = 一次 LLM 调用:
    1. 把完整对话（system + 历史 + 之前的工具结果）发给模型（流式）
    2. 流式消费: 文本增量实时 yield 给前端；tool_calls 分片拼装成完整调用
    3. 无工具调用 => 模型说完了，结束
    4. 有工具调用 => 逐个执行，结果以 role=tool 消息追加进对话
    5. 若调用了 FinalizeReport => yield 报告事件并终止（原项目 stopWhen 语义）
    6. 回到 1，直到 MAX_STEPS

【唯一的坑】OpenAI 流式下 tool_calls 是分片到达的:
    每个 chunk 的 delta.tool_calls 里，arguments 只是完整 JSON 的一个碎片
    （可能只有几个字符），必须按 index 累积拼接，流结束后才能 json.loads。
    见 _merge_tool_call_chunk。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from openai import AsyncOpenAI, OpenAIError

from app.agent.events import (
    AgentEvent,
    DoneEvent,
    ErrorEvent,
    ReportEvent,
    TextDelta,
    ToolCallEvent,
    ToolResultEvent,
)
from app.agent.prompts import build_system_prompt
from app.config import settings
from app.retrieval import current_question
from app.tools import TOOL_SCHEMAS, execute_tool, result_to_str

# 单个工具结果在【前端事件】里的最大长度（防止 read_file 大文件刷屏）。
# 注意：给模型的消息不截断——模型需要完整内容才能写对 SQL
MAX_EVENT_OUTPUT_CHARS = 4000

# 懒创建的模块级客户端（避免 import 时就要求配好 API key）
_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    return _client


@dataclass
class _PartialToolCall:
    """流式拼装中的单个工具调用。"""

    id: str = ""
    name: str = ""
    arguments: str = ""  # JSON 字符串碎片的累积


def _merge_tool_call_chunk(pending: dict[int, _PartialToolCall], tc_delta: Any) -> None:
    """把一个 tool_call 分片合并进拼装区。

    OpenAI 流式协议: 每个分片带 index 标识属于第几个工具调用；
    id/name 只在首个分片出现，arguments 逐片追加。
    """
    slot = pending.setdefault(tc_delta.index, _PartialToolCall())
    if tc_delta.id:
        slot.id = tc_delta.id
    if tc_delta.function:
        if tc_delta.function.name:
            slot.name = tc_delta.function.name
        if tc_delta.function.arguments:
            slot.arguments += tc_delta.function.arguments


def _parse_args(arguments_json: str) -> dict:
    """解析工具参数用于【前端展示】（执行层在 registry 里自行解析）。"""
    try:
        parsed = json.loads(arguments_json) if arguments_json.strip() else {}
        return parsed if isinstance(parsed, dict) else {"_raw": arguments_json}
    except json.JSONDecodeError:
        return {"_raw": arguments_json}


def _truncate_for_event(result: Any) -> tuple[Any, bool]:
    """截断过长的工具输出（仅用于前端事件，不影响给模型的消息）。"""
    text = result if isinstance(result, str) else None
    if text is not None and len(text) > MAX_EVENT_OUTPUT_CHARS:
        return text[:MAX_EVENT_OUTPUT_CHARS] + "\n... (已截断)", True
    return result, False


def _extract_question(messages: list[dict]) -> str | None:
    """取最后一条用户消息作为"当前问题"（供 VectorRetriever 预筛选用）。"""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return str(msg.get("content", ""))
    return None


async def run_agent(messages: list[dict]) -> AsyncIterator[AgentEvent]:
    """运行 Agent，流式产出事件。

    messages: OpenAI 格式的对话历史（不含 system，由本函数注入），
              前端每次携带完整历史，天然支持多轮对话。
    """
    # 把当前问题放进 request 级上下文 —— RAG 预筛选的数据通道
    # （PassthroughRetriever 忽略它；VectorRetriever 用它做向量召回）
    current_question.set(_extract_question(messages))

    # 本地副本：工具往返消息不断追加，但不污染调用方传入的列表
    convo: list[dict] = [
        {"role": "system", "content": build_system_prompt()},
        *messages,
    ]

    for _step in range(settings.max_steps):
        # ---- 1. 发起流式 LLM 调用 ----
        try:
            stream = await get_client().chat.completions.create(
                model=settings.model,
                messages=convo,
                tools=TOOL_SCHEMAS,
                stream=True,
            )
        except OpenAIError as e:
            yield ErrorEvent(message=f"LLM 调用失败: {e}")
            return

        # ---- 2. 消费流: 文本实时转发, tool_calls 分片拼装 ----
        text_parts: list[str] = []
        pending: dict[int, _PartialToolCall] = {}  # index -> 拼装中的调用

        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue  # 部分中转站会发空 choices 的心跳 chunk
                delta = chunk.choices[0].delta
                if delta.content:
                    text_parts.append(delta.content)
                    yield TextDelta(delta=delta.content)
                for tc in delta.tool_calls or []:
                    _merge_tool_call_chunk(pending, tc)
        except OpenAIError as e:
            yield ErrorEvent(message=f"流式响应中断: {e}")
            return

        # ---- 3. 无工具调用 => 模型直接回答完毕 ----
        if not pending:
            yield DoneEvent()
            return

        # ---- 4. 把 assistant 消息（含工具调用）追加进对话 ----
        # 必须原样回传 tool_calls，后续的 role=tool 消息靠 id 关联
        ordered = [pending[i] for i in sorted(pending)]
        convo.append({
            "role": "assistant",
            "content": "".join(text_parts) or None,
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in ordered
            ],
        })

        # ---- 5. 逐个执行工具 ----
        for call in ordered:
            yield ToolCallEvent(name=call.name, arguments=_parse_args(call.arguments))

            result = execute_tool(call.name, call.arguments)

            # 前端事件截断展示；模型消息保留全文（写 SQL 需要完整 schema）
            display, truncated = _truncate_for_event(result)
            yield ToolResultEvent(name=call.name, output=display, truncated=truncated)

            convo.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result_to_str(result),
            })

            # ---- 6. stopWhen: FinalizeReport 成功 => 终止 ----
            if call.name == "FinalizeReport" and isinstance(result, dict) and result.get("ok"):
                yield ReportEvent(
                    sql=result["sql"],
                    csv_results=result["csv_results"],
                    narrative=result["narrative"],
                )
                yield DoneEvent()
                return
            # 校验失败（ok=False）则不终止：模型会看到错误并补齐字段重试

    yield ErrorEvent(message=f"达到最大步数限制 ({settings.max_steps})，分析未完成")
