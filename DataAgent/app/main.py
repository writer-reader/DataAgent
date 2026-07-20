"""FastAPI 入口 —— /api/chat SSE 路由 + 静态前端托管。

对应原项目 src/app/api/chat/route.ts（那边返回 UI Message Stream，
这边返回自定义 SSE 事件流，协议见 app/agent/events.py）。

启动: uvicorn app.main:app --reload --port 8000
访问: http://localhost:8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agent import run_agent

app = FastAPI(title="DataAgent", description="Python 版 AI 数据分析师")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class ChatMessage(BaseModel):
    """单条对话消息（OpenAI 格式的子集，只允许 user/assistant）。"""

    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    """前端每次携带完整对话历史 => 服务端无状态，天然支持多轮。"""

    messages: list[ChatMessage] = Field(min_length=1)


@app.post("/api/chat")
async def chat(req: ChatRequest) -> EventSourceResponse:
    """运行 Agent，以 SSE 流式返回事件。

    SSE 格式: 每个事件一行 event: <type> + 一行 data: <json>。
    前端按 event 类型分发渲染（见 static/index.html）。
    """

    async def gen():
        try:
            async for event in run_agent([m.model_dump() for m in req.messages]):
                yield {
                    "event": event.type,
                    "data": event.model_dump_json(),
                }
        except Exception as e:  # 兜底：任何异常都以 error 事件收尾，前端不至于干等
            yield {
                "event": "error",
                "data": f'{{"type": "error", "message": "服务端异常: {type(e).__name__}"}}',
            }

    return EventSourceResponse(gen())


@app.get("/api/health")
async def health() -> JSONResponse:
    """健康检查（顺便暴露当前配置的模型名，方便排查）。"""
    from app.config import settings

    return JSONResponse({"ok": True, "model": settings.model})


# 静态前端挂在最后（根路径），避免覆盖 /api/* 路由
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
