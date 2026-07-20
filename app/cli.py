"""CLI 入口 —— 不起 Web 服务直接在终端问问题（P3 验收工具）。

用法:
    python -m app.cli "各行业分别有多少家公司？"
    python -m app.cli            # 进入交互模式，输入 exit 退出

rich 渲染: 工具调用过程灰色显示，最终报告以表格+面板呈现。
"""

from __future__ import annotations

import asyncio
import csv
import io
import sys

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from app.agent import run_agent
from app.agent.events import (
    DoneEvent,
    ErrorEvent,
    ReportEvent,
    TextDelta,
    ToolCallEvent,
    ToolResultEvent,
)

console = Console()


def _render_report(event: ReportEvent) -> None:
    """渲染最终报告: 叙述面板 + SQL 高亮 + CSV 转 rich 表格。"""
    console.print(Panel(event.narrative, title="分析结论", border_style="green"))
    if event.sql:
        console.print(Syntax(event.sql, "sql", theme="monokai", word_wrap=True))
    if event.csv_results.strip():
        rows = list(csv.reader(io.StringIO(event.csv_results)))
        if rows:
            table = Table(show_lines=False)
            for col in rows[0]:
                table.add_column(col, overflow="fold")
            for row in rows[1:51]:  # 终端最多展示 50 行
                table.add_row(*row)
            console.print(table)
            if len(rows) - 1 > 50:
                console.print(f"[dim]... 共 {len(rows) - 1} 行，仅显示前 50 行[/dim]")


async def ask(question: str, history: list[dict]) -> list[dict]:
    """问一个问题，流式打印过程，返回更新后的对话历史（支持多轮）。"""
    history.append({"role": "user", "content": question})
    answer_parts: list[str] = []

    async for event in run_agent(history):
        match event:
            case TextDelta():
                answer_parts.append(event.delta)
                console.print(event.delta, end="", style="dim")
            case ToolCallEvent():
                console.print(f"\n[cyan]▶ {event.name}[/cyan] [dim]{event.arguments}[/dim]")
            case ToolResultEvent():
                preview = str(event.output)
                if len(preview) > 200:
                    preview = preview[:200] + "..."
                console.print(f"[dim]  ↳ {preview}[/dim]")
            case ReportEvent():
                console.print()
                _render_report(event)
                answer_parts.append(event.narrative)
            case ErrorEvent():
                console.print(f"\n[red]错误: {event.message}[/red]")
            case DoneEvent():
                console.print()

    # 把本轮回答记入历史，多轮对话时模型能看到上下文
    history.append({"role": "assistant", "content": "".join(answer_parts) or "(完成)"})
    return history


def main() -> None:
    if len(sys.argv) > 1:
        # 单发模式: python -m app.cli "问题"
        asyncio.run(ask(" ".join(sys.argv[1:]), []))
        return

    # 交互模式
    console.print("[bold]DataAgent CLI[/bold] — 输入问题，exit 退出\n")
    history: list[dict] = []
    while True:
        try:
            question = console.input("[bold cyan]❯ [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in {"exit", "quit", "q"}:
            break
        if question:
            history = asyncio.run(ask(question, history))


if __name__ == "__main__":
    main()
